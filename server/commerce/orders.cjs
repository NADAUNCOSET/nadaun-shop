'use strict';
const crypto=require('node:crypto');
const {ShopError,hash,protect,sessions}=require('./security.cjs');
const {customerFields,quoteCatalog,positive}=require('./pricing.cjs');
const {matchPayment,receiptUrl}=require('./toss.cjs');
const {rentalSchedule,rentalCustomer,rentalQuote}=require('./rental.cjs');
const {evidenceFields,paymentEvidence}=require('./evidence.cjs');
const fulfillment=require('./fulfillment.cjs');
const {shippingLabels,labelView,labelPending}=require('./shipping-labels.cjs');
const uuid=()=>crypto.randomUUID();
function repository(db,clock=()=>Date.now()){
 const get=async id=>(await db.query('SELECT * FROM shop_orders WHERE id=?',[id]))[0]||null;
 async function patch(row,fields,actor,action,document=null,shippingJob=null){
  const allowed=new Set(['state','lines_json','subtotal','shipping','total','quote_version','quote_expires','payment_key','payment_mode','payment_provider','payment_auth_cipher','payment_receipt_cipher','paid_at','fulfillment','carrier','tracking','customer_cipher']);
  const keys=Object.keys(fields);if(!keys.length||keys.some(k=>!allowed.has(k)))throw Error('Invalid internal order update');
  const now=clock(),version=row.version+1;
  const result=await db.batch([
   {sql:`UPDATE shop_orders SET ${keys.map(k=>k+'=?').join(',')},updated_at=?,version=version+1 WHERE id=? AND version=? RETURNING *`,params:[...keys.map(k=>fields[k]),now,row.id,row.version]},
   {sql:'INSERT INTO shop_order_events(id,order_id,actor,action,created_at,version) SELECT ?,?,?,?,?,? WHERE changes()=1',params:[uuid(),row.id,actor,action,now,version]},
   ...(shippingJob?[{sql:'INSERT INTO shop_shipping_sync(order_id,next_attempt) SELECT ?,? WHERE changes()=1 ON CONFLICT(order_id) DO UPDATE SET next_attempt=excluded.next_attempt',params:[row.id,shippingJob.next_attempt]}]:[]),
   ...(document?[{sql:'INSERT INTO shop_documents(order_id,kind,status,result_cipher,created_at,updated_at,next_attempt) SELECT ?,?,?,?,?,?,? FROM shop_orders WHERE id=? AND version=? AND state=\'PAID\' ON CONFLICT(order_id) DO NOTHING',params:[row.id,document.kind,document.status,document.result_cipher,now,now,document.status==='issued'?now+86400000:0,row.id,version]}]:[]),
   ...(['CANCELED','PAYMENT_REVIEW'].includes(fields.state)?[{sql:"UPDATE shop_documents SET status='review',updated_at=?,version=version+1 WHERE order_id=? AND EXISTS(SELECT 1 FROM shop_orders WHERE id=? AND version=?)",params:[now,row.id,row.id,version]},
    {sql:"INSERT INTO shop_points(id,member_id,amount,reason,kind,request_key,fingerprint,actor,source_order,created_at) SELECT ?,member_id,-amount,'주문 취소·환불 확인에 따른 적립 회수','reversal','reverse:'||source_order,?, ?,source_order,? FROM shop_points WHERE source_order=? AND kind='purchase' AND EXISTS(SELECT 1 FROM shop_orders WHERE id=? AND version=? AND state IN ('CANCELED','PAYMENT_REVIEW')) ON CONFLICT(request_key) DO NOTHING",params:[uuid(),hash(row.id),actor,now,row.id,row.id,version]}]:[])
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
  shippingDue:async now=>db.query('SELECT order_id FROM shop_shipping_sync WHERE next_attempt IS NOT NULL AND next_attempt<=? ORDER BY next_attempt LIMIT 2',[now]),
  scheduleShipping:async(id,next)=>db.query('UPDATE shop_shipping_sync SET next_attempt=? WHERE order_id=?',[next,id]),
  calendar:async id=>(await db.query('SELECT status,event_url,error_code,checked_at FROM shop_calendar_sync WHERE order_id=?',[id]))[0]||null,
  calendarHealth:async()=>(await db.query("SELECT status,checked_at FROM shop_calendar_health WHERE id='calendar'"))[0]||null,
  customer:async owner=>db.query('SELECT * FROM shop_orders WHERE customer_hash=? ORDER BY created_at DESC LIMIT 50',[owner]),
  list:async()=>db.query('SELECT * FROM shop_orders ORDER BY created_at DESC LIMIT 100'),
  events:async id=>db.query('SELECT actor,action,created_at,version FROM shop_order_events WHERE order_id=? ORDER BY version',[id])};
}
function orderService({repo,catalog,detail,dataKey,sessionKey=dataKey,payment=null,documents=null,labelProvider=null,invoiceEnabled=false,testing=false,clock=()=>Date.now()}){
 const cipher=protect(dataKey),returns=sessions(sessionKey,clock);
 const dto=(row,admin=false)=>{
  const stored=cipher.decrypt(row.customer_cipher),customer=Object.fromEntries(Object.entries(stored).filter(([key])=>!key.startsWith('_admin_'))),rental=customer.rental||null,history=fulfillment.shipments(row,stored);
  return {id:row.id,kind:rental?'rental':'purchase',rental,purchase_workflow:fulfillment.purchaseWorkflow(row,stored),state:row.state,payment_mode:row.payment_mode,lines:JSON.parse(row.lines_json),subtotal:row.subtotal,shipping:row.shipping,total:row.total,quote_version:row.quote_version,quote_expires:row.quote_expires,fulfillment:row.fulfillment,carrier:row.carrier,tracking:row.tracking,shipments:fulfillment.publicShipments(history),created_at:row.created_at,updated_at:row.updated_at,version:row.version,evidence_kind:customer.evidence?.kind||'card_receipt',...(admin?{customer,admin_shipping_label:labelView(stored._admin_shipping_label),admin_note:stored._admin_note||null,admin_cancellation:stored._admin_cancellation||null,admin_cases:fulfillment.adminCases(stored._admin_cases||[],history)}:{})};
 };
 async function detailed(row,admin=false){
  const document=documents?await documents.get(row.id):null;
  if(document?.status==='issued'&&document.kind!=='tax_invoice'&&row.payment_provider==='toss'&&row.payment_receipt_cipher){const url=receiptUrl(cipher.decrypt(row.payment_receipt_cipher).receiptUrl);if(url)document.receipt_url=url;}
  return {...dto(row,admin),document,...(admin&&repo.calendar?{calendar:await repo.calendar(row.id)}:{})};
 }
 async function own(id,owner){const row=await repo.get(id);if(!row||row.customer_hash!==owner)throw new ShopError(404,'주문을 찾을 수 없습니다. 주문한 브라우저에서 다시 확인해주세요.');return row;}
 async function applyPayment(row,remote,actor='payment'){
  const status=matchPayment(remote,row);
  const next=status==='DONE'?'PAID':status==='CANCELED'?'CANCELED':status==='PARTIAL_CANCELED'?'PAYMENT_REVIEW':null;
  if(!next)throw new ShopError(503,'결제 결과를 확인 중입니다. 중복 결제하지 말고 잠시 후 주문 상태를 확인해주세요.');
  if(row.state===next)return row;
  if(row.state==='CANCELED')throw new ShopError(409,'취소된 결제의 상태 확인이 필요합니다.');
  try{return await repo.patch(row,{state:next},actor,'payment_'+status.toLowerCase());}
  catch(error){if(error.status===409){const current=await repo.get(row.id);if(current?.state===next&&current.payment_key===row.payment_key&&current.total===row.total)return current;}throw error;}
 }
 async function rentalMove(id,input,returning,actor){
  if(!payment)throw new ShopError(503,'토스페이먼츠 결제 서비스 연결을 준비 중입니다.');
  const row=await repo.get(id);if(!row)throw new ShopError(404,'렌탈 요청을 찾을 수 없습니다.');
  const customer=cipher.decrypt(row.customer_cipher);if(!customer.rental)throw new ShopError(409,'렌탈 요청에서만 방문 처리를 할 수 있습니다.');
  if(row.state!=='PAID'||row.payment_mode!=='live'||row.payment_provider!=='toss'||row.version!==input.version||row.fulfillment!==(returning?'processing':'unfulfilled'))throw new ShopError(409,'실결제가 확인된 최신 렌탈 상태를 다시 확인해주세요.');
  const verified=await applyPayment(row,await payment.get(row.payment_key),actor);if(verified.state!=='PAID')throw new ShopError(409,'결제 취소 또는 변경 상태를 확인해주세요.');
  customer.rental[returning?'actual_return_at':'actual_pickup_at']=clock();
  return dto(await repo.patch(row,{fulfillment:returning?'shipped':'processing',customer_cipher:cipher.encrypt(customer)},actor,returning?'rental_returned':'rental_picked_up'),true);
 }
 async function editable(id,input){
  if(typeof id!=='string'||!/^NS-[a-zA-Z0-9_-]{1,40}$/.test(id))throw new ShopError(400,'주문번호를 확인해주세요.');
  const row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');
  if(!Number.isSafeInteger(input.version)||input.version<0||input.version!==row.version)throw new ShopError(409,'주문 상태가 변경되었습니다. 새로고침 후 다시 확인해주세요.');
  return row;
 }
 function privateText(value,max,label,required=false){
  if(typeof value!=='string'||value.length>max||/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(value))throw new ShopError(400,label+'을 확인해주세요.');
  const text=value.trim();if(required&&text.length<2)throw new ShopError(400,label+'을 2자 이상 입력해주세요.');return text;
 }
 function purchaseCustomer(row){const customer=cipher.decrypt(row.customer_cipher);if(customer.rental)throw new ShopError(409,'렌탈은 방문 수령·반납 처리 기능을 이용해주세요.');return customer;}
 async function verifiedForShipping(row,actor){
  if(!payment)throw new ShopError(503,'토스페이먼츠 결제 서비스 연결을 준비 중입니다.');
  if(row.state!=='PAID'||row.payment_mode!=='live'||row.payment_provider!=='toss')throw new ShopError(409,'실결제가 확인된 최신 주문에서만 출고할 수 있습니다.');
  if((await applyPayment(row,await payment.get(row.payment_key),actor)).state!=='PAID')throw new ShopError(409,'결제 취소 또는 변경 상태를 확인해주세요.');
 }
 function rememberImport(customer,identity){
  if(!identity)return;
  const previous=customer._admin_imports||[];
  if(previous.length>=500)throw new ShopError(409,'이 주문의 파일 처리 이력이 500건에 도달했습니다. 개별 처리 기능을 이용해주세요.');
  customer._admin_imports=[...previous,{key:identity.key,fingerprint:identity.fingerprint,created_at:clock()}];
 }
 async function correctShipment(row,input,actor,identity){
  const customer=purchaseCustomer(row),history=fulfillment.shipments(row,customer),shipment=history.find(item=>item.id===input.shipment_id),shipping=fulfillment.tracking(input);
  if(!shipment)throw new ShopError(404,'수정할 출고 내역을 찾을 수 없습니다.');
  if(input.items!==undefined)throw new ShopError(400,'운송정보 수정으로 출고 품목이나 수량을 바꿀 수 없습니다.');
  if(shipment.actor==='goodsflow')throw new ShopError(409,'자동 발급 송장은 굿스플로 조회로 확인해주세요.');
  const before={carrier:shipment.carrier,tracking:shipment.tracking};
  Object.assign(shipment,shipping,{updated_at:clock(),updated_by:actor});
  shipment.corrections=[...(shipment.corrections||[]),{...before,changed_at:clock(),actor}];
  customer._admin_shipments=history;
  rememberImport(customer,identity);
  const lastOriginal=history.filter(item=>item.purpose==='original').at(-1);
  return detailed(await repo.patch(row,{customer_cipher:cipher.encrypt(customer),...(lastOriginal?.id===shipment.id?shipping:{})},actor,'order_tracking_updated'),true);
 }
 return {
  dto,invoiceEnabled,
  ...shippingLabels({repo,cipher,provider:labelProvider,editable,purchaseCustomer,verifiedForShipping,detailed,clock}),
  async workflow(id,input,actor='owner'){
   if(!['preparing','ready','delivered'].includes(input.stage))throw new ShopError(400,'상품 준비·배송 대기·배송 완료 중 처리 단계를 선택해주세요.');
   const row=await editable(id,input),customer=purchaseCustomer(row),history=fulfillment.shipments(row,customer);
   if(row.state!=='PAID'||row.payment_mode!=='live')throw new ShopError(409,'실결제 완료된 구매 주문에서만 배송 단계를 처리할 수 있습니다.');
   if(labelPending(customer)&&input.stage!=='delivered')throw new ShopError(409,'자동 송장 접수 후에는 배송 상태 조회를 이용해주세요.');
   if(input.stage==='delivered'){
    if(row.fulfillment!=='shipped'||!history.length||fulfillment.originalRemaining(row,history).length)throw new ShopError(409,'주문 상품을 모두 출고한 뒤 배송 완료를 확인해주세요.');
    if(history.filter(s=>s.purpose==='original').every(s=>s.delivered_at))throw new ShopError(409,'이미 배송 완료를 기록한 주문입니다.');
    for(const shipment of history.filter(s=>s.purpose==='original')){shipment.delivered_at=shipment.delivered_at||clock();shipment.delivery_confirmed_by=actor;shipment.delivery_source='manual';}
    customer._admin_shipments=history;
   }else if(row.fulfillment!=='unfulfilled'||history.length)throw new ShopError(409,'출고 전 주문만 준비·대기 단계로 변경할 수 있습니다.');
   if(input.stage!=='delivered'&&fulfillment.purchaseWorkflow(row,customer)?.stage===input.stage)throw new ShopError(409,'이미 같은 배송 단계입니다.');
   customer._admin_purchase_workflow={stage:input.stage,updated_at:clock(),actor};
   return detailed(await repo.patch(row,{customer_cipher:cipher.encrypt(customer)},actor,'purchase_'+input.stage),true);
  },
  async workflowBulk(input,actor='owner'){
   if(!['preparing','ready','delivered'].includes(input.stage)||!Array.isArray(input.orders)||!input.orders.length||input.orders.length>25)throw new ShopError(400,'한 번에 1~25건의 배송 단계만 처리할 수 있습니다.');
   const ids=new Set();for(const item of input.orders){if(!item||typeof item.id!=='string'||!/^NS-[a-zA-Z0-9_-]{1,40}$/.test(item.id)||!Number.isSafeInteger(item.version)||item.version<0||ids.has(item.id))throw new ShopError(400,'선택 주문번호·버전과 중복을 확인해주세요.');ids.add(item.id);}
   const results=[];
   for(const item of input.orders){try{results.push({id:item.id,ok:true,order:await this.workflow(item.id,{version:item.version,stage:input.stage},actor)});}catch(error){results.push({id:item.id,ok:false,status:error instanceof ShopError?error.status:503,error:error instanceof ShopError?error.message:'처리 결과를 다시 확인해주세요.'});}}
   return {results,succeeded:results.filter(r=>r.ok).length,failed:results.filter(r=>!r.ok).length};
  },
  async previewInvoice(id,input,identity){
   const row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');
   const customer=purchaseCustomer(row),previous=(customer._admin_imports||[]).find(item=>item.key===identity.key);
   if(previous){if(previous.fingerprint!==identity.fingerprint)throw new ShopError(409,'동일 파일 작업의 내용이 달라졌습니다.');return {duplicate:true,items:input.items||[]};}
   if(row.version!==input.version)throw new ShopError(409,'주문 버전이 변경되었습니다. 최신 주문으로 파일을 다시 확인해주세요.');
   fulfillment.tracking(input);const history=fulfillment.shipments(row,customer);
   if(input.operation==='update'){
    if(!history.some(s=>s.id===input.shipment_id))throw new ShopError(404,'수정할 출고 내역을 찾을 수 없습니다.');
    if(input.items!==undefined)throw new ShopError(400,'운송정보 수정은 상품 수량을 바꿀 수 없습니다.');
    return {duplicate:false,items:[]};
   }
   if(labelPending(customer))throw new ShopError(409,'자동 송장이 접수된 주문입니다. 송장 결과 조회를 이용해주세요.');
   if(input.operation!=='ship')throw new ShopError(400,'출고 또는 운송정보 수정 작업을 선택해주세요.');
   if(row.state!=='PAID'||row.payment_mode!=='live'||row.payment_provider!=='toss')throw new ShopError(409,'실결제 완료된 구매 주문만 출고할 수 있습니다.');
   if(row.fulfillment==='processing'&&!history.length)throw new ShopError(409,'기존 부분 출고의 품목 수량을 먼저 확인해주세요.');
   return {duplicate:false,items:fulfillment.selectItems(input.items,fulfillment.originalRemaining(row,history),{optional:true})};
  },
  async importInvoice(id,input,actor,identity){
   const check=await this.previewInvoice(id,input,identity);
   if(check.duplicate)return {duplicate:true,order:await this.adminGet(id)};
   const next={...input,...(input.operation==='ship'?{items:check.items}:{})};
   const order=input.operation==='ship'?await this.ship(id,next,actor,identity):await correctShipment(await editable(id,next),next,actor,identity);
   return {duplicate:false,order};
  },
  async pickup(id,input,actor='owner'){return rentalMove(id,input,false,actor);},
  async rentalReturn(id,input,actor='owner'){return rentalMove(id,input,true,actor);},
  async saveNote(id,input,actor='owner'){
   const text=privateText(input.note,2000,'내부 메모'),row=await editable(id,input);
   // Payment approval persists against this version. Do not create unrelated
   // conflicts while an external approval may still be in flight.
   if(['PAYMENT_PENDING','CONFIRMING'].includes(row.state))throw new ShopError(409,'결제 진행이 끝난 뒤 내부 메모를 저장해주세요.');
   const customer=cipher.decrypt(row.customer_cipher);customer._admin_note={text,updated_at:clock(),actor};
   return detailed(await repo.patch(row,{customer_cipher:cipher.encrypt(customer)},actor,text?'admin_note_updated':'admin_note_cleared'),true);
  },
  async cancelRequest(id,input,actor='owner'){
   const reason=privateText(input.reason,500,'접수 취소 사유',true),row=await editable(id,input);
   if(!['REQUESTED','APPROVED'].includes(row.state)||row.fulfillment!=='unfulfilled'||row.carrier||row.tracking||['payment_key','payment_mode','payment_provider','payment_auth_cipher','payment_receipt_cipher','paid_at'].some(key=>row[key]!=null))throw new ShopError(409,'결제가 시작되지 않은 미결제 접수만 취소할 수 있습니다. 결제·환불 상태는 별도로 확인해주세요.');
   const customer=cipher.decrypt(row.customer_cipher);customer._admin_cancellation={reason,created_at:clock(),actor};
   return detailed(await repo.patch(row,{state:'CANCELED',quote_expires:null,customer_cipher:cipher.encrypt(customer)},actor,'request_canceled'),true);
  },
  async updateShipment(id,input,actor='owner'){return correctShipment(await editable(id,input),input,actor);},
  async createCase(id,input,actor='owner'){
   const row=await editable(id,input),customer=purchaseCustomer(row),history=fulfillment.shipments(row,customer),cases=customer._admin_cases||[];
   if(!['return','exchange'].includes(input.kind))throw new ShopError(400,'반품 또는 교환을 선택해주세요.');
   if(row.payment_mode!=='live'||!['PAID','PAYMENT_REVIEW','CANCELED'].includes(row.state))throw new ShopError(409,'실제 출고한 구매 주문에서 반품·교환을 기록해주세요.');
   const shipment=history.find(s=>s.id===input.shipment_id);if(!shipment)throw new ShopError(404,'반품·교환 대상 출고 내역을 선택해주세요.');
   if(cases.length>=100)throw new ShopError(409,'반품·교환 기록이 많습니다. 기존 사건 내역을 먼저 확인해주세요.');
   const reason=privateText(input.reason,1000,'반품·교환 사유',true),items=fulfillment.selectItems(input.items,fulfillment.caseRemaining(shipment,cases)),now=clock();
   cases.push({id:'CS-'+uuid(),kind:input.kind,status:'requested',shipment_id:shipment.id,items,reason,note:'',return_carrier:'',return_tracking:'',created_at:now,updated_at:now,actor,updated_by:actor,history:[{status:'requested',note:'',created_at:now,actor}]});
   customer._admin_cases=cases;
   return detailed(await repo.patch(row,{customer_cipher:cipher.encrypt(customer)},actor,input.kind+'_case_created'),true);
  },
  async updateCase(id,input,actor='owner'){
   const row=await editable(id,input),customer=purchaseCustomer(row),cases=customer._admin_cases||[],item=cases.find(c=>c.id===input.case_id);
   if(!item)throw new ShopError(404,'반품·교환 기록을 찾을 수 없습니다.');
   const transitions={requested:['approved','rejected'],approved:['returning','received','rejected'],returning:['received','rejected'],received:['closed'],closed:[],rejected:[]};
   if(input.status!==item.status&&!transitions[item.status]?.includes(input.status))throw new ShopError(409,'현재 반품·교환 상태에서 가능한 다음 단계를 선택해주세요.');
   if(!Object.hasOwn(transitions,input.status))throw new ShopError(400,'반품·교환 상태를 확인해주세요.');
   const note=input.note===undefined?'':privateText(input.note,1000,'처리 메모');
   if(input.status!==item.status&&['closed','rejected'].includes(input.status)&&note.length<2)throw new ShopError(400,'기록 종결 또는 거절 사유를 처리 메모에 입력해주세요.');
   if(item.kind==='exchange'&&input.status==='closed'&&fulfillment.replacementRemaining(item,fulfillment.shipments(row,customer)).length)throw new ShopError(409,'교환품의 남은 수량을 출고한 뒤 기록을 종결해주세요.');
   if(input.carrier!==undefined||input.tracking!==undefined){const shipping=fulfillment.tracking(input);item.return_carrier=shipping.carrier;item.return_tracking=shipping.tracking;}
   const now=clock();item.status=input.status;item.note=note;item.updated_at=now;item.updated_by=actor;item.history.push({status:input.status,note,created_at:now,actor});
   customer._admin_cases=cases;
   return detailed(await repo.patch(row,{customer_cipher:cipher.encrypt(customer)},actor,'case_'+input.status),true);
  },
  async exchangeShip(id,input,actor='owner'){
   const row=await editable(id,input),customer=purchaseCustomer(row),history=fulfillment.shipments(row,customer),item=(customer._admin_cases||[]).find(c=>c.id===input.case_id);
   if(!item||item.kind!=='exchange'||item.status!=='received')throw new ShopError(409,'회수가 확인된 교환 기록에서 교환품을 출고해주세요.');
   const remaining=fulfillment.replacementRemaining(item,history);if(!remaining.length)throw new ShopError(409,'교환품이 이미 전량 출고되었습니다. 운송정보 수정 기능을 이용해주세요.');
   const items=fulfillment.selectItems(input.items,remaining,{optional:true}),shipping=fulfillment.tracking(input);
   await verifiedForShipping(row,actor);
   history.push({id:'SH-'+uuid(),purpose:'exchange',case_id:item.id,items,...shipping,created_at:clock(),updated_at:clock(),actor,updated_by:actor});customer._admin_shipments=history;
   item.updated_at=clock();item.updated_by=actor;item.history.push({status:item.status,note:'교환품 출고 기록',created_at:clock(),actor});
   return detailed(await repo.patch(row,{customer_cipher:cipher.encrypt(customer)},actor,'exchange_shipped'),true);
  },
  async create(owner,key,input){
   if(!/^[a-zA-Z0-9_-]{16,100}$/.test(key||''))throw new ShopError(400,'주문 요청 번호가 올바르지 않습니다.');
   const customer=customerFields(input.customer);customer.evidence=evidenceFields(input.evidence);
   if(customer.evidence.kind==='tax_invoice'&&!invoiceEnabled)throw new ShopError(503,'전자세금계산서 발급 연결을 준비 중입니다. 구매 상담을 이용해주세요.');
   const q=quoteCatalog(catalog,detail,input.items,clock),now=clock();
   const fingerprint=hash(JSON.stringify({customer,items:q.lines.map(p=>[p.id,p.option,p.quantity])}));
   const row=await repo.insert({id:'NS-'+uuid(),customer_hash:owner,request_key:key,fingerprint,state:'REQUESTED',customer_cipher:cipher.encrypt(customer),lines_json:JSON.stringify(q.lines),subtotal:q.subtotal,shipping:q.shipping,total:q.total,confirm_key:uuid(),created_at:now,updated_at:now});
   return dto(row);
  },
  async createRental(owner,key,input){
   if(!/^[a-zA-Z0-9_-]{16,100}$/.test(key||''))throw new ShopError(400,'렌탈 요청 번호가 올바르지 않습니다.');
   const customer=rentalCustomer(input.customer);customer.rental=rentalSchedule(input.rental,clock);customer.evidence=evidenceFields(input.evidence);
   if(customer.evidence.kind==='tax_invoice'&&!invoiceEnabled)throw new ShopError(503,'전자세금계산서 발급 연결을 준비 중입니다.');
   const q=rentalQuote(catalog,detail,input.items,null,clock),now=clock(),fingerprint=hash(JSON.stringify({kind:'rental',customer,items:q.lines.map(p=>[p.id,p.option,p.quantity])}));
   const row=await repo.insert({id:'NS-'+uuid(),customer_hash:owner,request_key:key,fingerprint,state:'REQUESTED',customer_cipher:cipher.encrypt(customer),lines_json:JSON.stringify(q.lines),subtotal:null,shipping:0,total:null,confirm_key:uuid(),created_at:now,updated_at:now});
   return dto(row);
  },
  async qaDeliver(id,input,actor){
   if(!testing)throw new ShopError(404,'요청을 찾을 수 없습니다.');const row=await editable(id,input),customer=purchaseCustomer(row);
   if(row.state!=='PAID'||row.payment_mode!=='test')throw new ShopError(409,'테스트 결제 완료 주문에서만 사용할 수 있습니다.');
   customer._admin_shipments=[{id:'SH-QA-'+uuid(),purpose:'original',items:JSON.parse(row.lines_json).map(({id,option,name,quantity})=>({id,option,name,quantity})),carrier:'테스트 배송',tracking:'0000000000',created_at:clock(),updated_at:clock(),delivered_at:clock(),delivery_source:'qa',actor,updated_by:actor}];
   return detailed(await repo.patch(row,{fulfillment:'shipped',customer_cipher:cipher.encrypt(customer)},actor,'qa_delivery_simulated'),true);
  },
  async qaCancel(id,input,actor){
   if(!testing||payment?.mode!=='test')throw new ShopError(404,'요청을 찾을 수 없습니다.');const row=await editable(id,input);
   if(row.payment_mode!=='test'||!row.payment_key||!['PAID','CANCELED'].includes(row.state))throw new ShopError(409,'테스트 결제 완료 주문을 확인해주세요.');
   await payment.netCancel({paymentKey:row.payment_key,orderId:row.id,amount:row.total},row,'나다운 쇼핑몰 전체 흐름 테스트 취소');
   if(row.state==='CANCELED')return detailed(row,true);return detailed(await repo.patch(row,{state:'CANCELED'},actor,'qa_payment_canceled'),true);
  },
  async list(owner){return Promise.all((await repo.customer(owner)).map(r=>detailed(r)));},
  async get(id,owner){return detailed(await own(id,owner));},
  async customerDocument(id,owner,print=false){
   const row=await own(id,owner);
   if(!documents||!payment)throw new ShopError(503,'증빙 연결을 확인하고 있습니다.');
   if(row.state!=='PAID')throw new ShopError(409,'결제 완료 주문의 증빙만 확인할 수 있습니다.');
   if(print)return {url:await documents.customerPrint(id)};
   await documents.process(id);return detailed(await own(id,owner));
  },
  async adminList(){return Promise.all((await repo.list()).map(r=>detailed(r,true)));},
  async adminDetail(row){return detailed(row,true);},
  async adminGet(id){const row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');return detailed(row,true);},
  async retryDocument(id){if(!documents||!payment)throw new ShopError(503,'증빙 서비스를 확인해주세요.');await documents.retry(id);const row=await repo.get(id);return detailed(row,true);},
  async approve(id,input,actor='owner'){
   const row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');
   if(!['REQUESTED','APPROVED'].includes(row.state)||input.version!==row.version||input.stock_confirmed!==true)throw new ShopError(409,'주문 상태와 재고·납기 확인을 다시 확인해주세요.');
   const customer=cipher.decrypt(row.customer_cipher);if(customer.rental)rentalSchedule(customer.rental,clock);
   const rows=JSON.parse(row.lines_json).map(p=>({id:p.id,option:p.option,quantity:p.quantity}));
   const q=customer.rental?rentalQuote(catalog,detail,rows,input.rental_prices??[],clock):quoteCatalog(catalog,detail,rows,clock);
   if(q.total===null)throw new ShopError(409,'금액 미확정 상품은 상담으로 견적을 확정해야 합니다.');
   return dto(await repo.patch(row,{state:'APPROVED',lines_json:JSON.stringify(q.lines),subtotal:q.subtotal,shipping:q.shipping,total:q.total,quote_version:row.quote_version+1,quote_expires:clock()+30*60*1000},actor,'quote_approved'),true);
  },
  async start(id,owner,version,device='WEB'){
   if(!payment)throw new ShopError(503,'토스페이먼츠 결제 서비스 연결을 준비 중입니다.');
   let row=await own(id,owner);
   if(!['APPROVED','PAYMENT_PENDING'].includes(row.state)||row.quote_version!==version||row.quote_expires<=clock()||!positive(row.total))throw new ShopError(409,'확정 금액과 결제 가능 시간을 다시 확인해주세요.');
   if(!['WEB','MOBILE'].includes(device))throw new ShopError(400,'결제 기기 정보를 확인해주세요.');
   if(row.state==='APPROVED')row=await repo.patch(row,{state:'PAYMENT_PENDING',payment_mode:payment.mode,payment_provider:'toss'},'customer','payment_started');
   if(row.payment_mode!==payment.mode||row.payment_provider!=='toss')throw new ShopError(409,'결제 환경이 변경되었습니다. 고객센터에 주문번호를 알려주세요.');
   const token=returns.issue(row.id+'|'+row.confirm_key+'|'+payment.mode,'payment',Math.max(1,Math.floor((row.quote_expires-clock())/1000)));
   const customer=cipher.decrypt(row.customer_cipher);
   if(customer.evidence?.kind==='tax_invoice'&&!invoiceEnabled)throw new ShopError(503,'전자세금계산서 설정 확인이 필요합니다.');
   return payment.prepare(row,customer,token,device);
  },
  async acceptReturn(input){
   if(!payment)throw new ShopError(503,'토스페이먼츠 결제 서비스 연결을 준비 중입니다.');
   const subject=returns.read(input.token,'payment');
   if(!subject)throw new ShopError(401,'결제 인증 유효 시간이 지났습니다. 주문 상태를 확인해주세요.');
   const [id,nonce,mode]=subject.split('|');let row=await repo.get(id);
   if(!row||row.confirm_key!==nonce||row.payment_mode!==mode||payment.mode!==mode||row.payment_provider!=='toss')throw new ShopError(409,'주문의 결제 환경 확인이 필요합니다.');
   const auth=payment.validateAuthentication(input,row);
   if(row.payment_auth_cipher){
    const original=cipher.decrypt(row.payment_auth_cipher);
    if(original.paymentKey!==auth.paymentKey||original.orderId!==auth.orderId||original.amount!==auth.amount)throw new ShopError(409,'이미 다른 결제 인증이 연결된 주문입니다.');
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
  async reconcile(id,input={},actor='owner'){
   if(!payment)throw new ShopError(503,'토스페이먼츠 결제 서비스 연결을 준비 중입니다.');
   const row=await repo.get(id);if(!row)throw new ShopError(404,'확인할 결제 정보가 없습니다.');
   if(row.payment_mode!==payment.mode||row.payment_provider!=='toss')throw new ShopError(409,'주문의 결제 환경 확인이 필요합니다.');
   if(row.payment_key)return dto(await applyPayment(row,await payment.get(row.payment_key),actor),true);
   if(row.state==='CANCELED')return dto(row,true);
   // A crashed approval has no trusted persisted approval. Do not reapprove it.
   if(row.payment_auth_cipher&&['CONFIRMING','PAYMENT_REVIEW'].includes(row.state)){
    if(clock()-row.updated_at<60000)throw new ShopError(409,'승인 요청이 진행 중입니다. 잠시 후 다시 확인해주세요.');
    const canceled=await payment.netCancel(cipher.decrypt(row.payment_auth_cipher),row);
    if(canceled.canceled)return dto(await repo.patch(row,{state:'CANCELED'},actor,'payment_net_canceled'),true);
   }
   throw new ShopError(503,'토스페이먼츠 관리자에서 결제 결과를 확인해야 합니다.');
  },
  async ship(id,input,actor='owner',identity=null){
   const row=await editable(id,input),customer=purchaseCustomer(row),history=fulfillment.shipments(row,customer);
   if(labelPending(customer))throw new ShopError(409,'자동 송장이 접수된 주문입니다. 송장 결과 조회를 이용해주세요.');
   // Preserve the legacy completed-order tracking edit without creating another
   // shipment. New history must always identify the shipment being corrected.
   const originals=history.filter(s=>s.purpose==='original');
   if(row.fulfillment==='shipped'&&originals.length===1&&originals[0].id==='legacy'&&input.items===undefined)return correctShipment(row,{...input,shipment_id:'legacy'},actor);
   if(row.fulfillment==='processing'&&!history.length)throw new ShopError(409,'기존 부분 출고의 품목 수량을 먼저 확인해주세요.');
   const remaining=fulfillment.originalRemaining(row,history);if(!remaining.length)throw new ShopError(409,'이미 전량 출고되었습니다. 출고 내역에서 운송정보를 수정해주세요.');
   const items=fulfillment.selectItems(input.items,remaining,{optional:true}),shipping=fulfillment.tracking(input);
   await verifiedForShipping(row,actor);
   history.push({id:'SH-'+uuid(),purpose:'original',items,...shipping,created_at:clock(),updated_at:clock(),actor,updated_by:actor});customer._admin_shipments=history;rememberImport(customer,identity);
   const complete=fulfillment.originalRemaining(row,history).length===0;
   return detailed(await repo.patch(row,{fulfillment:complete?'shipped':'processing',...shipping,customer_cipher:cipher.encrypt(customer)},actor,complete?'order_shipped':'order_partially_shipped'),true);
  }
 };
}
module.exports={repository,orderService};
