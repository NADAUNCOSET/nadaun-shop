'use strict';
const crypto=require('node:crypto');
const {protect,ShopError}=require('./security.cjs');
const {matchPayment}=require('./inicis.cjs');
const {paymentEvidence}=require('./evidence.cjs');
const managementKey=id=>'NS'+crypto.createHash('sha256').update(id).digest('hex').slice(0,22);
function documentService({db,repo,dataKey,payment,invoice=null,clock=()=>Date.now()}){
 const cipher=protect(dataKey);
 const get=async id=>(await db.query('SELECT * FROM shop_documents WHERE order_id=?',[id]))[0]||null;
 function dto(row){
  if(!row)return null;
  const result=row.result_cipher?cipher.decrypt(row.result_cipher):{};
  return {kind:row.kind,status:row.status,purpose:result.purpose||null,approval_number:result.approval_number||null,issued_at:result.issued_at||null,nts_status:result.nts_status||null,updated_at:row.updated_at};
 }
 async function finish(job,status,result){
  await db.query("UPDATE shop_documents SET status=?,result_cipher=?,lease_until=0,next_attempt=?,updated_at=?,attempts=CASE WHEN ?='issued' THEN 0 ELSE attempts END,version=version+1 WHERE order_id=? AND version=?",
   [status,cipher.encrypt(result),clock()+(status==='issued'?(result.nts_status==='pending'?300000:86400000):Math.min(3600000,60000*2**Math.min(job.attempts,6))),clock(),status,job.order_id,job.version]);
  return dto(await get(job.order_id));
 }
 async function process(id){
  let job=await get(id);if(!job)return null;
  if(['review','voided'].includes(job.status)||job.next_attempt>clock()||job.lease_until>clock())return dto(job);
  const claimed=await db.query("UPDATE shop_documents SET status='processing',lease_until=?,attempts=attempts+1,updated_at=?,version=version+1 WHERE order_id=? AND version=? AND lease_until<=? RETURNING *",[clock()+120000,clock(),id,job.version,clock()]);
  if(!claimed.length)return dto(await get(id));job=claimed[0];
  try{
   const order=await repo.get(id);
   if(!order||order.state!=='PAID')return finish(job,'review',{reason:'payment_not_paid'});
   if(order.payment_mode!==payment.mode||order.payment_provider!=='inicis')return finish(job,'review',{reason:'payment_environment_mismatch'});
   const customer=cipher.decrypt(order.customer_cipher),stored=cipher.decrypt(order.payment_receipt_cipher);
   // Before any delayed external issue, recheck the transaction with the PG.
   const remote=await payment.get(order.payment_key);
   const paymentState=matchPayment(remote,order);
   if(paymentState!=='DONE'){
    await repo.patch(order,{state:paymentState==='CANCELED'?'CANCELED':'PAYMENT_REVIEW'},'payment','document_payment_changed');
    return dto(await get(id));
   }
   if(job.kind!=='tax_invoice'){
    const verifiedReceipt=remote.cashReceipt?.issued&&stored.cashReceipt?.amount===order.total&&stored.cashReceipt?.purpose?{...stored.cashReceipt,...remote.cashReceipt,amount:stored.cashReceipt.amount,purpose:stored.cashReceipt.purpose}:remote.cashReceipt;
    const evidence=paymentEvidence({...remote,cashReceipt:verifiedReceipt},customer.evidence,order.total);
    return finish(job,job.attempts>=5&&evidence.status==='retry'?'review':evidence.status,evidence);
   }
   if(remote.method!=='BANK'||(remote.cashReceipt?.issued||remote.cashReceipt?.present)||stored.cashReceipt?.issued)return finish(job,'review',{reason:'duplicate_evidence_or_wrong_method'});
   if(!invoice||invoice.mode!==order.payment_mode)return finish(job,'review',{reason:'invoice_not_configured'});
   const key=managementKey(id);
   // The provider key never changes, including after an ambiguous timeout or
   // process crash. Look up the existing document before attempting an issue.
   let result=await invoice.lookup(key,order,customer.evidence);
   if(!result&&cipher.decrypt(job.result_cipher).approval_number)return finish(job,'review',{...cipher.decrypt(job.result_cipher),reason:'issued_document_missing'});
   if(!result)result=await invoice.issue(key,order,customer.evidence,stored.approvedAt);
   if(!result?.issued||!result.approval_number)throw Error('Invoice not confirmed');
   return finish(job,'issued',result);
  }catch{
   const prior=cipher.decrypt(job.result_cipher);
   return finish(job,job.attempts>=5?'review':prior.approval_number?'issued':'retry',{...prior,reason:'provider_confirmation_pending'});
  }
 }
 return {get:async id=>dto(await get(id)),process,
  async drain(limit=4){const rows=await db.query("SELECT order_id FROM shop_documents WHERE status IN ('queued','retry','processing','issued') AND next_attempt<=? AND lease_until<=? ORDER BY next_attempt,created_at LIMIT ?",[clock(),clock(),Math.min(10,limit)]);for(const row of rows)await process(row.order_id);return {processed:rows.length};},
  async retry(id){const row=await get(id);if(!row)throw new ShopError(404,'증빙 요청이 없습니다.');if(row.status==='issued'||row.status==='voided'||row.lease_until>clock())return dto(row);await db.query("UPDATE shop_documents SET status='retry',next_attempt=0,attempts=0,version=version+1 WHERE order_id=? AND version=?",[id,row.version]);return process(id);}
 };
}
module.exports={documentService,managementKey};
