'use strict';
const crypto=require('node:crypto');
const {ShopError,hash,protect,sessions}=require('./security.cjs');
const {customerFields,quoteCatalog,positive}=require('./pricing.cjs');
const {matchPayment}=require('./inicis.cjs');
const {evidenceFields,paymentEvidence}=require('./evidence.cjs');
const uuid=()=>crypto.randomUUID();
function repository(db,clock=()=>Date.now()){
 const get=async id=>(await db.query('SELECT * FROM shop_orders WHERE id=?',[id]))[0]||null;
 async function patch(row,fields,actor,action,document=null){
  const allowed=new Set(['state','lines_json','subtotal','shipping','total','quote_version','quote_expires','payment_key','payment_mode','payment_provider','payment_auth_cipher','payment_receipt_cipher','paid_at','fulfillment','carrier','tracking']);
  const keys=Object.keys(fields);if(!keys.length||keys.some(k=>!allowed.has(k)))throw Error('Invalid internal order update');
  const now=clock(),version=row.version+1;
  const result=await db.batch([
   {sql:`UPDATE shop_orders SET ${keys.map(k=>k+'=?').join(',')},updated_at=?,version=version+1 WHERE id=? AND version=? RETURNING *`,params:[...keys.map(k=>fields[k]),now,row.id,row.version]},
   {sql:'INSERT INTO shop_order_events(id,order_id,actor,action,created_at,version) SELECT ?,?,?,?,?,? WHERE changes()=1',params:[uuid(),row.id,actor,action,now,version]},
   ...(document?[{sql:'INSERT INTO shop_documents(order_id,kind,status,result_cipher,created_at,updated_at,next_attempt) SELECT ?,?,?,?,?,?,? FROM shop_orders WHERE id=? AND version=? AND state=\'PAID\' ON CONFLICT(order_id) DO NOTHING',params:[row.id,document.kind,document.status,document.result_cipher,now,now,document.status==='issued'?now+86400000:0,row.id,version]}]:[]),
   ...(['CANCELED','PAYMENT_REVIEW'].includes(fields.state)?[{sql:"UPDATE shop_documents SET status='review',updated_at=?,version=version+1 WHERE order_id=? AND EXISTS(SELECT 1 FROM shop_orders WHERE id=? AND version=?)",params:[now,row.id,row.id,version]}]:[])
  ]);
  if(!result[0].length)throw new ShopError(409,'주문 상태가 변경되었습니다. 새로고침 후 다시 확인해주세요.');
  return result[0][0];
 }
 async function insert(row){
  const keys=Object.keys(row),now=clock();
  const result=await db.batch([
   {sql:`INSERT INTO shop_orders(${keys.join(',')}) VALUES(${keys.map(()=>'?').join(',')}) ON CONFLICT(customer_hash,request_key) DO NOTHING`,params:keys.map(k=>row[k])},
   {sql:'INSERT INTO shop_order_events(id,order_id,actor,action,created_at,version) SELECT ?,?,?,?,?,0 WHERE changes()=1',params:[uuid(),row.id,'customer','order_requested',now]},
   {sql:'SELECT * FROM shop_orders WHERE customer_hash=? AND request_key=?',params:[row.customer_hash,row.request_key]}
  ]);
  const saved=result[2][0];if(!saved||saved.fingerprint!==row.fingerprint)throw new ShopError(409,'같은 요청 번호의 주문 내용이 달라졌습니다. 주문서를 다시 열어주세요.');return saved;
 }
 async function limit(key,max=30,seconds=60){
  const now=clock(),bucket=key+':'+Math.floor(now/(seconds*1000));
  const result=await db.batch([
   {sql:'DELETE FROM shop_rate_limits WHERE expires_at < ?',params:[now]},
   {sql:'INSERT INTO shop_rate_limits(key,attempts,expires_at) VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET attempts=attempts+1 RETURNING attempts',params:[bucket,now+seconds*2000]}
  ]);const rows=result[1];
  if(rows[0].attempts>max)throw new ShopError(429,'요청이 많습니다. 잠시 후 다시 시도해주세요.');
 }
 return {get,patch,insert,limit,
  customer:async owner=>db.query('SELECT * FROM shop_orders WHERE customer_hash=? ORDER BY created_at DESC LIMIT 50',[owner]),
  list:async()=>db.query('SELECT * FROM shop_orders ORDER BY created_at DESC LIMIT 100'),
  events:async id=>db.query('SELECT actor,action,created_at,version FROM shop_order_events WHERE order_id=? ORDER BY version',[id])};
}
function orderService({repo,catalog,detail,dataKey,sessionKey=dataKey,payment=null,documents=null,invoiceEnabled=false,clock=()=>Date.now()}){
 const cipher=protect(dataKey),returns=sessions(sessionKey,clock);
 const dto=(row,admin=false)=>({id:row.id,state:row.state,payment_mode:row.payment_mode,lines:JSON.parse(row.lines_json),subtotal:row.subtotal,shipping:row.shipping,total:row.total,quote_version:row.quote_version,quote_expires:row.quote_expires,fulfillment:row.fulfillment,carrier:row.carrier,tracking:row.tracking,created_at:row.created_at,updated_at:row.updated_at,version:row.version,evidence_kind:cipher.decrypt(row.customer_cipher).evidence?.kind||'card_receipt',...(admin?{customer:cipher.decrypt(row.customer_cipher)}:{})});
 async function detailed(row,admin=false){
  const document=documents?await documents.get(row.id):null;
  if(document?.status==='issued'&&document.kind!=='tax_invoice'&&row.payment_provider==='inicis'&&/^[a-zA-Z0-9_-]{10,40}$/.test(row.payment_key||''))document.receipt_url='https://iniweb.inicis.com/DefaultWebApp/mall/cr/cm/mCmReceipt_head.jsp?noTid='+encodeURIComponent(row.payment_key)+'&noMethod=1';
  return {...dto(row,admin),document};
 }
 async function own(id,owner){const row=await repo.get(id);if(!row||row.customer_hash!==owner)throw new ShopError(404,'주문을 찾을 수 없습니다. 주문한 브라우저에서 다시 확인해주세요.');return row;}
 async function applyPayment(row,remote){
  const status=matchPayment(remote,row);
  const next=status==='DONE'?'PAID':status==='CANCELED'?'CANCELED':status==='PARTIAL_CANCELED'?'PAYMENT_REVIEW':null;
  if(!next)throw new ShopError(503,'결제 결과를 확인 중입니다. 중복 결제하지 말고 잠시 후 주문 상태를 확인해주세요.');
  if(row.state===next)return row;
  if(row.state==='CANCELED')throw new ShopError(409,'취소된 결제의 상태 확인이 필요합니다.');
  try{return await repo.patch(row,{state:next},'payment','payment_'+status.toLowerCase());}
  catch(error){if(error.status===409){const current=await repo.get(row.id);if(current?.state===next&&current.payment_key===row.payment_key&&current.total===row.total)return current;}throw error;}
 }
 return {
  dto,invoiceEnabled,
  async create(owner,key,input){
   if(!/^[a-zA-Z0-9_-]{16,100}$/.test(key||''))throw new ShopError(400,'주문 요청 번호가 올바르지 않습니다.');
   const customer=customerFields(input.customer);customer.evidence=evidenceFields(input.evidence);
   if(customer.evidence.kind==='tax_invoice'&&!invoiceEnabled)throw new ShopError(503,'전자세금계산서 발급 연결을 준비 중입니다. 구매 상담을 이용해주세요.');
   const q=quoteCatalog(catalog,detail,input.items,clock),now=clock();
   const fingerprint=hash(JSON.stringify({customer,items:q.lines.map(p=>[p.id,p.option,p.quantity])}));
   const row=await repo.insert({id:'NS-'+uuid(),customer_hash:owner,request_key:key,fingerprint,state:'REQUESTED',customer_cipher:cipher.encrypt(customer),lines_json:JSON.stringify(q.lines),subtotal:q.subtotal,shipping:q.shipping,total:q.total,confirm_key:uuid(),created_at:now,updated_at:now});
   return dto(row);
  },
  async list(owner){return Promise.all((await repo.customer(owner)).map(r=>detailed(r)));},
  async get(id,owner){return detailed(await own(id,owner));},
  async adminList(){return Promise.all((await repo.list()).map(r=>detailed(r,true)));},
  async adminDetail(row){return detailed(row,true);},
  async adminGet(id){const row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');return detailed(row,true);},
  async retryDocument(id){if(!documents||!payment)throw new ShopError(503,'증빙 서비스를 확인해주세요.');await documents.retry(id);const row=await repo.get(id);return detailed(row,true);},
  async approve(id,input){
   const row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');
   if(!['REQUESTED','APPROVED'].includes(row.state)||input.version!==row.version||input.stock_confirmed!==true)throw new ShopError(409,'주문 상태와 재고·납기 확인을 다시 확인해주세요.');
   const q=quoteCatalog(catalog,detail,JSON.parse(row.lines_json).map(p=>({id:p.id,option:p.option,quantity:p.quantity})),clock);
   if(q.total===null)throw new ShopError(409,'금액 미확정 상품은 상담으로 견적을 확정해야 합니다.');
   return dto(await repo.patch(row,{state:'APPROVED',lines_json:JSON.stringify(q.lines),subtotal:q.subtotal,shipping:q.shipping,total:q.total,quote_version:row.quote_version+1,quote_expires:clock()+30*60*1000},'owner','quote_approved'),true);
  },
  async start(id,owner,version,device='WEB'){
   if(!payment)throw new ShopError(503,'이니시스 결제 서비스 연결을 준비 중입니다.');
   let row=await own(id,owner);
   if(!['APPROVED','PAYMENT_PENDING'].includes(row.state)||row.quote_version!==version||row.quote_expires<=clock()||!positive(row.total))throw new ShopError(409,'확정 금액과 결제 가능 시간을 다시 확인해주세요.');
   if(!['WEB','MOBILE'].includes(device))throw new ShopError(400,'결제 기기 정보를 확인해주세요.');
   if(row.state==='APPROVED')row=await repo.patch(row,{state:'PAYMENT_PENDING',payment_mode:payment.mode,payment_provider:'inicis'},'customer','payment_started');
   if(row.payment_mode!==payment.mode||row.payment_provider!=='inicis')throw new ShopError(409,'결제 환경이 변경되었습니다. 고객센터에 주문번호를 알려주세요.');
   const token=returns.issue(row.id+'|'+row.confirm_key+'|'+payment.mode,'payment',Math.max(1,Math.floor((row.quote_expires-clock())/1000)));
   const customer=cipher.decrypt(row.customer_cipher);
   if(customer.evidence?.kind==='tax_invoice'&&!invoiceEnabled)throw new ShopError(503,'전자세금계산서 설정 확인이 필요합니다.');
   return payment.prepare(row,customer,token,device);
  },
  async acceptReturn(input){
   if(!payment)throw new ShopError(503,'이니시스 결제 서비스 연결을 준비 중입니다.');
   const subject=returns.read(input.P_NOTI,'payment');
   if(!subject)throw new ShopError(401,'결제 인증 유효 시간이 지났습니다. 주문 상태를 확인해주세요.');
   const [id,nonce,mode]=subject.split('|');let row=await repo.get(id);
   if(!row||row.confirm_key!==nonce||row.payment_mode!==mode||payment.mode!==mode||row.payment_provider!=='inicis')throw new ShopError(409,'주문의 결제 환경 확인이 필요합니다.');
   if(input.P_STATUS!=='00')return dto(row);
   const auth=payment.validateAuthentication(input,row);
   if(row.payment_auth_cipher){
    const original=cipher.decrypt(row.payment_auth_cipher);
    if(original.P_AUTH_TID!==auth.P_AUTH_TID||original.P_IDCNAME!==auth.P_IDCNAME)throw new ShopError(409,'이미 다른 결제 인증이 연결된 주문입니다.');
    // A duplicate callback must never send a second approval or cancel a
    // concurrent approval. Recovery is a separate operator inquiry/cancellation.
    return dto(row);
   }
   if(row.state!=='PAYMENT_PENDING'||row.quote_expires<=clock())throw new ShopError(409,'현재 주문 상태에서는 결제를 승인할 수 없습니다.');
   row=await repo.patch(row,{state:'CONFIRMING',payment_auth_cipher:cipher.encrypt(auth)},'payment','payment_confirming');
   let approved;
   try{
    approved=await payment.approve(auth,row);
    matchPayment(approved,{...row,payment_key:approved.paymentKey});
    const selection=cipher.decrypt(row.customer_cipher).evidence;
    const evidence=paymentEvidence(approved,selection,row.total);
    row=await repo.patch(row,{state:'PAID',payment_key:approved.paymentKey,paid_at:clock(),payment_receipt_cipher:cipher.encrypt({...approved,approvedAt:approved.approvedAt||clock()})},'payment','payment_done',{kind:evidence.kind,status:evidence.status,result_cipher:cipher.encrypt(evidence)});
   }catch{
    // Resolve an ambiguous DB response before attempting compensation.
    let current;try{current=await repo.get(row.id);}catch{}
    if(approved&&current?.state==='PAID'&&current.payment_key===approved.paymentKey)return detailed(current);
    let canceled=false;try{canceled=(await payment.netCancel(auth,row)).canceled===true;}catch{}
    try{await repo.patch(current||row,{state:canceled?'CANCELED':'PAYMENT_REVIEW'},'payment',canceled?'payment_net_canceled':'payment_review');}catch{}
    throw new ShopError(503,canceled?'결제 승인을 완료하지 못해 취소 처리했습니다. 주문 상태를 확인해주세요.':'결제 결과를 확인해야 합니다. 중복 결제하지 말고 고객센터에 주문번호를 알려주세요.');
   }
   // Document delivery failure never cancels a successfully persisted payment.
   if(documents){try{await documents.process(row.id);}catch{}}
   return detailed(row);
  },
  async reconcile(id){
   if(!payment)throw new ShopError(503,'이니시스 결제 서비스 연결을 준비 중입니다.');
   const row=await repo.get(id);if(!row)throw new ShopError(404,'확인할 결제 정보가 없습니다.');
   if(row.payment_mode!==payment.mode||row.payment_provider!=='inicis')throw new ShopError(409,'주문의 결제 환경 확인이 필요합니다.');
   if(row.payment_key)return dto(await applyPayment(row,await payment.get(row.payment_key)),true);
   if(row.state==='CANCELED')return dto(row,true);
   // A crashed approval has no trusted approval TID. Do not reapprove it.
   if(row.payment_auth_cipher&&['CONFIRMING','PAYMENT_REVIEW'].includes(row.state)){
    if(clock()-row.updated_at<60000)throw new ShopError(409,'승인 요청이 진행 중입니다. 잠시 후 다시 확인해주세요.');
    const canceled=await payment.netCancel(cipher.decrypt(row.payment_auth_cipher),row);
    if(canceled.canceled)return dto(await repo.patch(row,{state:'CANCELED'},'owner','payment_net_canceled'),true);
   }
   throw new ShopError(503,'이니시스 관리자에서 결제 결과를 확인해야 합니다.');
  },
  async ship(id,input){
   if(!payment)throw new ShopError(503,'이니시스 결제 서비스 연결을 준비 중입니다.');
   const row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');
   if(row.state!=='PAID'||row.payment_mode!=='live'||row.payment_provider!=='inicis'||row.version!==input.version)throw new ShopError(409,'실결제가 확인된 최신 주문에서만 출고할 수 있습니다.');
   const verified=await applyPayment(row,await payment.get(row.payment_key));
   if(verified.state!=='PAID')throw new ShopError(409,'결제 취소 또는 변경 상태를 확인해주세요.');
   if(!/^[가-힣a-zA-Z0-9 .-]{2,40}$/.test(input.carrier||'')||!/^\d[\d-]{5,29}$/.test(input.tracking||''))throw new ShopError(400,'택배사와 운송장 번호를 확인해주세요.');
   return dto(await repo.patch(row,{fulfillment:'shipped',carrier:input.carrier,tracking:input.tracking},'owner','order_shipped'),true);
  }
 };
}
module.exports={repository,orderService};
