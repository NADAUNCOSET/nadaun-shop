'use strict';
const crypto=require('node:crypto');
const {ShopError,hash,protect}=require('./security.cjs');
const {customerFields,quoteCatalog,positive}=require('./pricing.cjs');
const {matchPayment}=require('./toss.cjs');
const uuid=()=>crypto.randomUUID();
function repository(db,clock=()=>Date.now()){
 const get=async id=>(await db.query('SELECT * FROM shop_orders WHERE id=?',[id]))[0]||null;
 async function patch(row,fields,actor,action){
  const allowed=new Set(['state','lines_json','subtotal','shipping','total','quote_version','quote_expires','payment_key','payment_mode','fulfillment','carrier','tracking']);
  const keys=Object.keys(fields);if(!keys.length||keys.some(k=>!allowed.has(k)))throw Error('Invalid internal order update');
  const now=clock(),version=row.version+1;
  const result=await db.batch([
   {sql:`UPDATE shop_orders SET ${keys.map(k=>k+'=?').join(',')},updated_at=?,version=version+1 WHERE id=? AND version=? RETURNING *`,params:[...keys.map(k=>fields[k]),now,row.id,row.version]},
   {sql:'INSERT INTO shop_order_events(id,order_id,actor,action,created_at,version) SELECT ?,?,?,?,?,? WHERE changes()=1',params:[uuid(),row.id,actor,action,now,version]}
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
function orderService({repo,catalog,detail,dataKey,payment=null,clock=()=>Date.now()}){
 const cipher=protect(dataKey);
 const dto=(row,admin=false)=>({id:row.id,state:row.state,payment_mode:row.payment_mode,lines:JSON.parse(row.lines_json),subtotal:row.subtotal,shipping:row.shipping,total:row.total,quote_version:row.quote_version,quote_expires:row.quote_expires,fulfillment:row.fulfillment,carrier:row.carrier,tracking:row.tracking,created_at:row.created_at,updated_at:row.updated_at,version:row.version,...(admin?{customer:cipher.decrypt(row.customer_cipher)}:{})});
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
  dto,
  async create(owner,key,input){
   if(!/^[a-zA-Z0-9_-]{16,100}$/.test(key||''))throw new ShopError(400,'주문 요청 번호가 올바르지 않습니다.');
   const customer=customerFields(input.customer),q=quoteCatalog(catalog,detail,input.items,clock),now=clock();
   const fingerprint=hash(JSON.stringify({customer,items:q.lines.map(p=>[p.id,p.option,p.quantity])}));
   const row=await repo.insert({id:'NS-'+uuid(),customer_hash:owner,request_key:key,fingerprint,state:'REQUESTED',customer_cipher:cipher.encrypt(customer),lines_json:JSON.stringify(q.lines),subtotal:q.subtotal,shipping:q.shipping,total:q.total,confirm_key:uuid(),created_at:now,updated_at:now});
   return dto(row);
  },
  async list(owner){return (await repo.customer(owner)).map(r=>dto(r));},
  async get(id,owner){return dto(await own(id,owner));},
  async adminList(){return (await repo.list()).map(r=>dto(r,true));},
  async approve(id,input){
   const row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');
   if(!['REQUESTED','APPROVED'].includes(row.state)||input.version!==row.version||input.stock_confirmed!==true)throw new ShopError(409,'주문 상태와 재고·납기 확인을 다시 확인해주세요.');
   const q=quoteCatalog(catalog,detail,JSON.parse(row.lines_json).map(p=>({id:p.id,option:p.option,quantity:p.quantity})),clock);
   if(q.total===null)throw new ShopError(409,'금액 미확정 상품은 상담으로 견적을 확정해야 합니다.');
   return dto(await repo.patch(row,{state:'APPROVED',lines_json:JSON.stringify(q.lines),subtotal:q.subtotal,shipping:q.shipping,total:q.total,quote_version:row.quote_version+1,quote_expires:clock()+30*60*1000},'owner','quote_approved'),true);
  },
  async start(id,owner,version){
   if(!payment)throw new ShopError(503,'결제 서비스 연결을 준비 중입니다.');
   let row=await own(id,owner);
   if(!['APPROVED','PAYMENT_PENDING'].includes(row.state)||row.quote_version!==version||row.quote_expires<=clock()||!positive(row.total))throw new ShopError(409,'확정 금액과 결제 가능 시간을 다시 확인해주세요.');
   if(row.state==='APPROVED')row=await repo.patch(row,{state:'PAYMENT_PENDING',payment_mode:payment.mode},'customer','payment_started');
   if(row.payment_mode!==payment.mode)throw new ShopError(409,'결제 환경이 변경되었습니다. 고객센터에 주문번호를 알려주세요.');
   return {orderId:row.id,amount:row.total,orderName:JSON.parse(row.lines_json)[0].name.slice(0,80)+(JSON.parse(row.lines_json).length>1?' 외':''),clientKey:payment.clientKey,mode:payment.mode};
  },
  async confirm(id,owner,input){
   if(!payment)throw new ShopError(503,'결제 서비스 연결을 준비 중입니다.');
   let row=await own(id,owner);
   if(row.payment_mode!==payment.mode)throw new ShopError(409,'주문의 결제 환경 확인이 필요합니다.');
   if(!/^[a-zA-Z0-9_-]{10,200}$/.test(input.paymentKey||'')||input.amount!==row.total)throw new ShopError(409,'주문 결제 정보가 일치하지 않습니다.');
   if(row.payment_key&&row.payment_key!==input.paymentKey)throw new ShopError(409,'이미 다른 결제 정보가 연결된 주문입니다.');
   if(row.state==='PAID')return dto(row);
   if(!['PAYMENT_PENDING','CONFIRMING','PAYMENT_REVIEW'].includes(row.state))throw new ShopError(409,'현재 주문 상태에서는 결제를 승인할 수 없습니다.');
   if(row.state==='PAYMENT_PENDING'){
    if(row.quote_expires<=clock())throw new ShopError(409,'결제 확인 시간이 지났습니다. 주문 상태를 다시 확인해주세요.');
    row=await repo.patch(row,{state:'CONFIRMING',payment_key:input.paymentKey},'customer','payment_confirming');
    // Pin order/key/amount before the external effect. The same key is reused
    // after response loss; redirect parameters alone never mark an order paid.
    try{await payment.confirm({paymentKey:row.payment_key,orderId:row.id,amount:row.total},row.confirm_key);}catch{/* Always query the authoritative result below. */}
   }
   let remote=await payment.get(row.payment_key);
   const status=matchPayment(remote,row);
   if(['READY','IN_PROGRESS'].includes(status)&&row.quote_expires>clock()){
    try{await payment.confirm({paymentKey:row.payment_key,orderId:row.id,amount:row.total},row.confirm_key);}catch{/* Recovery uses the persisted idempotency key. */}
    remote=await payment.get(row.payment_key);
   }
   return dto(await applyPayment(row,remote));
  },
  async reconcile(id){
   if(!payment)throw new ShopError(503,'결제 서비스 연결을 준비 중입니다.');
   const row=await repo.get(id);if(!row?.payment_key)throw new ShopError(404,'확인할 결제 정보가 없습니다.');
   if(row.payment_mode!==payment.mode)throw new ShopError(409,'주문의 결제 환경 확인이 필요합니다.');
   return dto(await applyPayment(row,await payment.get(row.payment_key)),true);
  },
  async ship(id,input){
   const row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');
   if(row.state!=='PAID'||row.payment_mode!=='live'||row.version!==input.version)throw new ShopError(409,'실결제가 확인된 최신 주문에서만 출고할 수 있습니다.');
   if(!/^[가-힣a-zA-Z0-9 .-]{2,40}$/.test(input.carrier||'')||!/^\d[\d-]{5,29}$/.test(input.tracking||''))throw new ShopError(400,'택배사와 운송장 번호를 확인해주세요.');
   return dto(await repo.patch(row,{fulfillment:'shipped',carrier:input.carrier,tracking:input.tracking},'owner','order_shipped'),true);
  }
 };
}
module.exports={repository,orderService};
