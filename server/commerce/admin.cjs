'use strict';
const {ShopError,protect}=require('./security.cjs');
const crypto=require('node:crypto');
const finance=require('./lifecycle.cjs');
const fulfillment=require('./fulfillment.cjs');
const STATES=['REQUESTED','APPROVED','PAYMENT_PENDING','CONFIRMING','PAID','PAYMENT_REVIEW','CANCELED'];
const STATE_NAMES={REQUESTED:'재고·납기 확인 중',APPROVED:'결제 가능',PAYMENT_PENDING:'결제 진행 중',CONFIRMING:'결제 결과 확인 중',PAID:'결제 완료',PAYMENT_REVIEW:'결제 확인 필요',CANCELED:'취소 완료'};
const KIND_NAMES={card_receipt:'카드 매출전표',cash_receipt:'현금영수증',tax_invoice:'전자세금계산서'};
// rentalQuote has always persisted pickup on every line; purchase quotes use
// standard/heavy_stand. Reuse that server-owned snapshot without decrypting PII
// for an entire year or introducing a live database migration.
const RENTAL_SQL="(json_array_length(o.lines_json)>0 AND NOT EXISTS (SELECT 1 FROM json_each(o.lines_json) line WHERE COALESCE(json_extract(line.value,'$.shipping_class'),'')!='pickup'))";
// Operational events are non-PII and transactionally recorded with the encrypted
// workflow ledger. Existing shipped orders remain in transit until manual proof.
const WORKFLOW_SQL=`CASE WHEN o.state='PAID' AND o.payment_mode='live' AND NOT ${RENTAL_SQL} THEN CASE
 WHEN o.fulfillment='shipped' AND EXISTS(SELECT 1 FROM shop_order_events we WHERE we.order_id=o.id AND we.action IN ('purchase_delivered','shipping_label_delivered')) THEN 'delivered'
 WHEN o.fulfillment!='unfulfilled' THEN 'in_transit'
 WHEN (SELECT we.action FROM shop_order_events we WHERE we.order_id=o.id AND we.action IN ('purchase_preparing','purchase_ready') ORDER BY we.version DESC LIMIT 1)='purchase_ready' THEN 'ready'
 ELSE 'preparing' END ELSE NULL END`;
const CASES_SQL="EXISTS(SELECT 1 FROM shop_order_events ce WHERE ce.order_id=o.id AND ce.action IN ('return_case_created','exchange_case_created'))";
const LIFECYCLE_SQL={
 'cancel-requests':"(SELECT ce.action FROM shop_order_events ce WHERE ce.order_id=o.id AND ce.action IN ('customer_cancel_requested','customer_cancel_resolved','refund_completed','refund_partial_completed','payment_canceled') ORDER BY ce.version DESC LIMIT 1)='customer_cancel_requested'",
 'refund-review':"(SELECT ce.action FROM shop_order_events ce WHERE ce.order_id=o.id AND ce.action IN ('refund_requested','refund_completed','refund_partial_completed') ORDER BY ce.version DESC LIMIT 1)='refund_requested'",
 'purchase-confirmed':"o.state='PAID' AND EXISTS(SELECT 1 FROM shop_order_events ce WHERE ce.order_id=o.id AND ce.action='purchase_confirmed')"
};
const QUEUE_STAGE={'purchase-preparing':'preparing','purchase-ready':'ready','purchase-transit':'in_transit','purchase-delivered':'delivered'};
const SEARCH_FIELDS=['all','order','customer','tracking'];
const encryptedSearch=f=>!!f.search&&f.searchField!=='order';
const normalize=value=>String(value||'').normalize('NFKC').toLocaleLowerCase('ko-KR').replace(/\s/g,'');
const digits=value=>String(value||'').replace(/[^0-9]/g,'');
function selectedIds(value){
 if(value===undefined)return null;
 if(!Array.isArray(value)||!value.length||value.length>50||value.some(id=>typeof id!=='string'||!/^NS-[a-zA-Z0-9_-]{1,40}$/.test(id))||new Set(value).size!==value.length)throw new ShopError(400,'중복 없는 주문번호 1~50건을 선택해주세요.');
 return value;
}
const offset=9*3600000;
const kstDate=ms=>new Date(ms+offset).toISOString().slice(0,10);
const kstTime=ms=>Number.isFinite(ms)?new Date(ms+offset).toISOString().slice(0,19).replace('T',' '):'';
function date(value){
 if(typeof value!=='string'||!/^20\d{2}-\d{2}-\d{2}$/.test(value))throw new ShopError(400,'조회 기간을 확인해주세요.');
 const ms=Date.parse(value+'T00:00:00+09:00');
 if(!Number.isFinite(ms)||kstDate(ms)!==value)throw new ShopError(400,'조회 날짜를 확인해주세요.');return ms;
}
function filters(input={},clock=()=>Date.now()){
 const year=kstDate(clock()).slice(0,4),from=input.from||year+'-01-01',to=input.to||year+'-12-31';
 const start=date(from),end=date(to)+86400000;
 if(end<=start||end-start>366*86400000)throw new ShopError(400,'한 번에 최대 1년의 자료를 조회할 수 있습니다.');
 const basis=input.basis||'created',mode=input.mode||'operational',state=input.state||'',fulfillment=input.fulfillment||'',document=input.document||'',kind=input.kind||'',queue=input.queue||'',search=typeof input.search==='string'?input.search.trim():input.search==null?'':null,searchField=input.searchField||'all',ids=selectedIds(input.ids);
 if(!['created','paid'].includes(basis)||!['operational','live','test','all'].includes(mode)||state&&!STATES.includes(state)||fulfillment&&!['unfulfilled','processing','shipped'].includes(fulfillment)||document&&!['queued','processing','issued','retry','review','voided','missing'].includes(document)||kind&&!['purchase','rental'].includes(kind)||queue&&!['purchase-shipping','rental-pickup','rental-return','payment-review','purchase-cases',...Object.keys(QUEUE_STAGE),...Object.keys(LIFECYCLE_SQL)].includes(queue)||!SEARCH_FIELDS.includes(searchField)||search===null||search.length>80||/[\x00-\x1f]/.test(search))throw new ShopError(400,'조회 조건을 확인해주세요.');
 const page=Number(input.page||1);if(!Number.isSafeInteger(page)||page<1||page>100000)throw new ShopError(400,'페이지를 확인해주세요.');
 return {from,to,start,end,basis,mode,state,fulfillment,document,kind,queue,search,searchField,...(ids?{ids}:{}),page};
}
function where(f){
 const time=f.basis==='paid'?"COALESCE(o.paid_at,(SELECT e.created_at FROM shop_order_events e WHERE e.order_id=o.id AND e.action='payment_done' LIMIT 1))":'o.created_at';
 const terms=[time+'>=?',time+'<?'],params=[f.start,f.end];
 if(f.mode==='operational')terms.push("(o.payment_mode IS NULL OR o.payment_mode='live')");
 else if(f.mode!=='all'){terms.push('o.payment_mode=?');params.push(f.mode);}
 for(const [field,value] of [['state',f.state],['fulfillment',f.fulfillment]])if(value){terms.push('o.'+field+'=?');params.push(value);}
 if(f.kind)terms.push((f.kind==='purchase'?'NOT ':'')+RENTAL_SQL);
 if(LIFECYCLE_SQL[f.queue])terms.push('('+LIFECYCLE_SQL[f.queue]+')');
 else if(QUEUE_STAGE[f.queue]){terms.push(`(${WORKFLOW_SQL})=?`);params.push(QUEUE_STAGE[f.queue]);}
 else if(f.queue==='purchase-cases')terms.push(CASES_SQL);
 else if(f.queue==='payment-review')terms.push("o.state IN ('CONFIRMING','PAYMENT_REVIEW')");
 else if(f.queue){terms.push("o.state='PAID'","o.payment_mode='live'",(f.queue==='purchase-shipping'?'NOT ':'')+RENTAL_SQL);terms.push(f.queue==='purchase-shipping'?"o.fulfillment!='shipped'":f.queue==='rental-pickup'?"o.fulfillment='unfulfilled'":"o.fulfillment='processing'");}
 if(f.document==='missing')terms.push('d.order_id IS NULL');else if(f.document){terms.push('d.status=?');params.push(f.document);}
 if(f.ids){terms.push(`o.id IN (${f.ids.map(()=>'?').join(',')})`);params.push(...f.ids);}
 if(f.search&&!encryptedSearch(f)){terms.push("(instr(lower(o.id),lower(?))>0 OR instr(lower(COALESCE(o.payment_key,'')),lower(?))>0)");params.push(f.search,f.search);}
 return {sql:terms.join(' AND '),params};
}
const csvCell=value=>{
 if(value==null)return '""';let text=String(value);
 if(typeof value!=='number'&&(/^[\s]*[=+\-@]/.test(text)||/^[\t\r\n]/.test(text)||/^0\d/.test(text)))text="'"+text;
 return '"'+text.replace(/"/g,'""')+'"';
};
const csv=rows=>'\ufeff'+rows.map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n';
function adminService({db,service,dataKey,clock=()=>Date.now()}){
 const cipher=protect(dataKey);
 const digest=value=>crypto.createHash('sha256').update(value).digest('hex');
 const sign=value=>crypto.createHmac('sha256',dataKey).update('invoice-preview-v1:'+value).digest('base64url');
 async function invoicePreview(input,actor){
  const file=await fulfillment.invoiceFile(input),file_hash=digest(file.bytes),groups=new Map(),errors=[];
  for(const [index,values] of file.rows.entries()){
   const number=index+2;
   try{
    if(values.length!==9||values.some(v=>typeof v!=='string'||/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(v)))throw new ShopError(400,'지정된 9개 열을 확인해주세요.');
    const [operation,id,version,shipment_id,carrier,tracking,item_id,option,quantity]=values.map(v=>v.trim());
    if(!['ship','update'].includes(operation)||!/^NS-[a-zA-Z0-9_-]{1,40}$/.test(id)||!/^\d{1,9}$/.test(version))throw new ShopError(400,'작업·주문번호·버전을 확인해주세요.');
    if(operation==='ship'&&shipment_id||operation==='update'&&!shipment_id)throw new ShopError(400,'출고 작업은 출고ID를 비우고, 운송정보 수정은 출고ID를 입력해주세요.');
    fulfillment.tracking({carrier,tracking});
    const hasItem=!!(item_id||option||quantity);
    if(operation==='update'&&hasItem||hasItem&&(!item_id||!/^\d{1,6}$/.test(quantity)||Number(quantity)<1))throw new ShopError(400,'품목 ID·옵션·양의 정수 수량을 확인해주세요.');
    const operationInput={operation,id,version:Number(version),shipment_id,carrier,tracking},signature=JSON.stringify(operationInput),group=groups.get(id);
    if(group&&(group.signature!==signature||!hasItem||group.all))throw new ShopError(400,'같은 주문의 작업·운송정보 중복 또는 전량/품목 혼합을 확인해주세요.');
    const current=group||{signature,input:operationInput,rows:[],all:!hasItem,items:[],invalid:false};
    current.rows.push(number);if(hasItem)current.items.push({id:item_id,option,quantity:Number(quantity)});groups.set(id,current);
   }catch(error){errors.push({rows:[number],error:error instanceof ShopError?error.message:'행 내용을 확인해주세요.'});}
  }
  if(groups.size>100)throw new ShopError(413,'송장 파일은 주문 100건까지 지원합니다.');
  const operations=[];
  for(const [id,group] of groups){
   const raw={...group.input,...(!group.all?{items:group.items}:{})},identity={key:digest(file_hash+':'+id),fingerprint:digest(JSON.stringify(raw))};
   try{
    const check=await service.previewInvoice(id,raw,identity),input={...raw,...(raw.operation==='ship'?{items:check.items}:{})};
    operations.push({index:operations.length,rows:group.rows,...input,duplicate:check.duplicate,identity});
   }catch(error){errors.push({rows:group.rows,error:error instanceof ShopError?error.message:'주문 내용을 확인할 수 없습니다.'});}
  }
  const expires_at=clock()+30*60000,valid=errors.length===0&&operations.length>0;
  const payload=Buffer.from(JSON.stringify({v:1,actor,file_hash,expires_at,operations})).toString('base64url');
  return {valid,file_hash,expires_at,operations:operations.map(({identity,...op})=>op),errors,totals:{rows:file.rows.length,orders:groups.size,items:operations.reduce((n,op)=>n+(op.items||[]).reduce((m,item)=>m+item.quantity,0),0)},...(valid?{preview_token:payload+'.'+sign(payload)}:{})};
 }
 async function invoiceApply(input,actor){
  if(typeof input.preview_token!=='string'||input.preview_token.length>1000000||!Number.isSafeInteger(input.index)||input.index<0)throw new ShopError(400,'송장 미리보기와 실행 행을 확인해주세요.');
  const parts=input.preview_token.split('.');if(parts.length!==2||!parts.every(p=>/^[a-zA-Z0-9_-]+$/.test(p)))throw new ShopError(400,'송장 미리보기를 다시 실행해주세요.');
  const expected=Buffer.from(sign(parts[0])),actual=Buffer.from(parts[1]);
  if(expected.length!==actual.length||!crypto.timingSafeEqual(expected,actual))throw new ShopError(403,'검증되지 않은 송장 미리보기입니다.');
  let data;try{data=JSON.parse(Buffer.from(parts[0],'base64url'));}catch{throw new ShopError(400,'송장 미리보기를 다시 실행해주세요.');}
  if(data.v!==1||data.actor!==actor||data.expires_at<=clock()||!Array.isArray(data.operations)||!data.operations[input.index])throw new ShopError(409,'송장 미리보기가 만료되거나 계정이 변경되었습니다. 다시 확인해주세요.');
  const operation=data.operations[input.index],{identity,rows,index,duplicate,...value}=operation;
  return {index,id:value.id,ok:true,...await service.importInvoice(value.id,value,actor,identity)};
 }
 function records(row){
  const customer=cipher.decrypt(row.customer_cipher),doc=row.doc_result?cipher.decrypt(row.doc_result):null;
  let receipt=null;if(row.payment_receipt_cipher)receipt=cipher.decrypt(row.payment_receipt_cipher);
  const verified=!!receipt&&receipt.provider==='toss'&&receipt.orderId===row.id&&receipt.paymentKey===row.payment_key&&receipt.totalAmount===row.total&&receipt.currency==='KRW'&&['DONE','CANCELED','PARTIAL_CANCELED'].includes(receipt.status);
  const paidAt=row.paid_at||row.confirmed_at||null;
  return {row,customer,doc,receipt,verified,paidAt};
 }
 function matches(row,f){
  const q=normalize(f.search),numeric=/^[0-9\s()+-]+$/.test(f.search)?digits(f.search):'',c=cipher.decrypt(row.customer_cipher);
  const customer=normalize(c.name).includes(q)||(numeric.length>0&&digits(c.phone).includes(numeric));
  const tracking=[row.tracking,...fulfillment.shipments(row,c).map(s=>s.tracking)].some(value=>normalize(value).includes(q)||(numeric.length>0&&digits(value).includes(numeric)));
  return f.searchField==='customer'?customer:f.searchField==='tracking'?tracking:customer||tracking||normalize(row.id).includes(q)||normalize(row.payment_key).includes(q);
 }
 async function query(f,limit,offsetRows=0){
  const w=where(f),scan=encryptedSearch(f),paged=scan||limit>500,rows=[];let cursor=null;
  // D1 responses stay bounded; a stable keyset avoids OFFSET shifts between
  // batches. Customer searches must finish the bounded scan before returning.
  do{
   const params=[...w.params],clause=cursor?' AND (o.created_at<? OR (o.created_at=? AND o.id<?))':'';
   if(cursor)params.push(cursor.created_at,cursor.created_at,cursor.id);
   const remaining=(scan?10001:limit)-rows.length,size=paged?Math.min(500,remaining):limit;
   const batch=await db.query(`SELECT o.*,d.kind AS doc_kind,d.status AS doc_status,d.result_cipher AS doc_result,
    d.attempts AS doc_attempts,d.updated_at AS doc_updated_at,(${LIFECYCLE_SQL['cancel-requests']}) AS cancel_requested,(${LIFECYCLE_SQL['refund-review']}) AS refund_pending,(${LIFECYCLE_SQL['purchase-confirmed']}) AS purchase_confirmed,${WORKFLOW_SQL} AS workflow_stage,${CASES_SQL} AS has_cases,
    (SELECT e.created_at FROM shop_order_events e WHERE e.order_id=o.id AND e.action='payment_done' LIMIT 1) AS confirmed_at
    FROM shop_orders o LEFT JOIN shop_documents d ON d.order_id=o.id WHERE ${w.sql}${clause}
    ORDER BY o.created_at DESC,o.id DESC LIMIT ? OFFSET ?`,[...params,size,paged?0:offsetRows]);
   rows.push(...batch);if(!paged||batch.length<size||rows.length>=(scan?10001:limit))break;cursor=batch.at(-1);
  }while(true);
  if(!scan)return rows;
  if(rows.length>10000)throw new ShopError(413,'고객·송장 검색은 조회 범위 1만 건까지 지원합니다. 기간을 줄여주세요.');
  return rows.filter(row=>matches(row,f)).slice(offsetRows,offsetRows+limit);
 }
 function matchesFilters(row,f){
  const lines=JSON.parse(row.lines_json),rental=lines.length>0&&lines.every(line=>line.shipping_class==='pickup');
  if(f.state&&row.state!==f.state||f.fulfillment&&row.fulfillment!==f.fulfillment||f.kind&&(f.kind==='rental')!==rental)return false;
  if(f.document&&(f.document==='missing'?!!row.doc_kind:row.doc_status!==f.document))return false;
  if(LIFECYCLE_SQL[f.queue])return !!row[{'cancel-requests':'cancel_requested','refund-review':'refund_pending','purchase-confirmed':'purchase_confirmed'}[f.queue]];
  if(QUEUE_STAGE[f.queue])return row.workflow_stage===QUEUE_STAGE[f.queue];
  if(f.queue==='purchase-cases')return !!row.has_cases;
  if(f.queue==='payment-review')return ['CONFIRMING','PAYMENT_REVIEW'].includes(row.state);
  if(f.queue){if(row.state!=='PAID'||row.payment_mode!=='live')return false;
   if(f.queue==='purchase-shipping')return !rental&&row.fulfillment!=='shipped';
   if(f.queue==='rental-pickup')return rental&&row.fulfillment==='unfulfilled';
   if(f.queue==='rental-return')return rental&&row.fulfillment==='processing';
  }return true;
 }
 function countRows(rows){
  const out={cancelRequested:0,refundPending:0,purchaseConfirmed:0,orders:rows.length,requested:0,approved:0,canceled:0,toShip:0,rentalPickup:0,rentalReturn:0,paymentReview:0,documentPending:0,approvedTotal:0,canceledOriginalTotal:0,purchasePreparing:0,purchaseReady:0,purchaseTransit:0,purchaseDelivered:0,purchaseCases:0};
  for(const row of rows){
   const rental=JSON.parse(row.lines_json).length>0&&JSON.parse(row.lines_json).every(line=>line.shipping_class==='pickup'),paid=row.state==='PAID'&&row.payment_mode==='live';
   if(row.state==='REQUESTED')out.requested++;if(row.state==='APPROVED')out.approved++;if(row.state==='CANCELED')out.canceled++;
   if(paid&&!rental&&row.fulfillment!=='shipped')out.toShip++;
   if(paid&&rental&&row.fulfillment==='unfulfilled')out.rentalPickup++;if(paid&&rental&&row.fulfillment==='processing')out.rentalReturn++;
   if(['CONFIRMING','PAYMENT_REVIEW'].includes(row.state))out.paymentReview++;
   if(['queued','processing','retry','review'].includes(row.doc_status))out.documentPending++;
   if(row.payment_mode==='live'&&row.payment_key&&row.payment_receipt_cipher){out.approvedTotal+=row.total;if(row.state==='CANCELED')out.canceledOriginalTotal+=row.total;}
   const key={preparing:'purchasePreparing',ready:'purchaseReady',in_transit:'purchaseTransit',delivered:'purchaseDelivered'}[row.workflow_stage];if(key)out[key]++;
   if(row.has_cases)out.purchaseCases++;if(row.cancel_requested)out.cancelRequested++;if(row.refund_pending)out.refundPending++;if(row.purchase_confirmed)out.purchaseConfirmed++;
  }return out;
 }
 async function summary(f){
  if(encryptedSearch(f))return countRows(await query(f,10001));
  const w=where(f);
  const rows=await db.query(`SELECT COUNT(*) AS orders,
   SUM(CASE WHEN ${LIFECYCLE_SQL['cancel-requests']} THEN 1 ELSE 0 END) AS cancelRequested,
   SUM(CASE WHEN ${LIFECYCLE_SQL['refund-review']} THEN 1 ELSE 0 END) AS refundPending,
   SUM(CASE WHEN ${LIFECYCLE_SQL['purchase-confirmed']} THEN 1 ELSE 0 END) AS purchaseConfirmed,
   SUM(CASE WHEN (${WORKFLOW_SQL})='preparing' THEN 1 ELSE 0 END) AS purchasePreparing,
   SUM(CASE WHEN (${WORKFLOW_SQL})='ready' THEN 1 ELSE 0 END) AS purchaseReady,
   SUM(CASE WHEN (${WORKFLOW_SQL})='in_transit' THEN 1 ELSE 0 END) AS purchaseTransit,
   SUM(CASE WHEN (${WORKFLOW_SQL})='delivered' THEN 1 ELSE 0 END) AS purchaseDelivered,
   SUM(CASE WHEN ${CASES_SQL} THEN 1 ELSE 0 END) AS purchaseCases,
   SUM(CASE WHEN o.state='REQUESTED' THEN 1 ELSE 0 END) AS requested,
   SUM(CASE WHEN o.state='APPROVED' THEN 1 ELSE 0 END) AS approved,
   SUM(CASE WHEN o.state='CANCELED' THEN 1 ELSE 0 END) AS canceled,
   SUM(CASE WHEN o.state='PAID' AND o.fulfillment!='shipped' AND o.payment_mode='live' AND NOT ${RENTAL_SQL} THEN 1 ELSE 0 END) AS toShip,
   SUM(CASE WHEN o.state='PAID' AND o.fulfillment='unfulfilled' AND o.payment_mode='live' AND ${RENTAL_SQL} THEN 1 ELSE 0 END) AS rentalPickup,
   SUM(CASE WHEN o.state='PAID' AND o.fulfillment='processing' AND o.payment_mode='live' AND ${RENTAL_SQL} THEN 1 ELSE 0 END) AS rentalReturn,
   SUM(CASE WHEN o.state IN ('CONFIRMING','PAYMENT_REVIEW') THEN 1 ELSE 0 END) AS paymentReview,
   SUM(CASE WHEN d.status IN ('queued','processing','retry','review') THEN 1 ELSE 0 END) AS documentPending,
   SUM(CASE WHEN o.payment_mode='live' AND o.payment_key IS NOT NULL AND o.payment_receipt_cipher IS NOT NULL THEN o.total ELSE 0 END) AS approvedTotal,
   SUM(CASE WHEN o.state='CANCELED' AND o.payment_mode='live' AND o.payment_key IS NOT NULL AND o.payment_receipt_cipher IS NOT NULL THEN o.total ELSE 0 END) AS canceledOriginalTotal
   FROM shop_orders o LEFT JOIN shop_documents d ON d.order_id=o.id WHERE ${w.sql}`,w.params);
  return Object.fromEntries(Object.entries(rows[0]).map(([k,v])=>[k,Number(v)||0]));
 }
 const notices=[
  '금액 단위: 원(KRW). 승인 금액에는 배송비가 포함됩니다.',
  '결제확정일 기준은 서버에 승인 성공을 저장한 시각(한국 시간)입니다. PG 승인일은 별도 열에 표시합니다.',
  '기본 운영 조회 및 다운로드는 테스트 결제를 제외합니다. 테스트 자료는 별도 조건에서 확인하세요.',
  '승인 누계와 취소 주문의 원 승인액은 별도 값입니다. 취소 발생일/부분 환불액/PG 수수료/실입금액은 PG 정산명세와 대조해야 합니다.',
  '이 자료는 주문·결제·발급 처리 내역입니다. 세무 신고 및 토스페이먼츠 정산명세를 대체하지 않습니다.',
  '필터에 해당하는 전체 주문 또는 명시적으로 선택한 주문을 다운로드합니다.',
  '반품·교환의 기록 종결은 환불 완료를 뜻하지 않습니다. 실제 환불은 PG 거래 내역과 별도로 대조하세요.'
 ];
 return {
  invoicePreview,invoiceApply,
  async list(input){
   const f=filters(input,clock),pageSize=25;
   const workloadFilters={...f,state:'',fulfillment:'',document:'',kind:'',queue:''};
   const sameWorkload=!f.state&&!f.fulfillment&&!f.document&&!f.kind&&!f.queue;
   if(encryptedSearch(f)){
    const candidates=await query(workloadFilters,10001),matches=candidates.filter(row=>matchesFilters(row,f)),counts=countRows(matches);
    return {orders:await Promise.all(matches.slice((f.page-1)*pageSize,f.page*pageSize).map(row=>service.adminDetail(row))),summary:counts,workload:countRows(candidates),filters:f,page:f.page,pageSize,pages:Math.max(1,Math.ceil(counts.orders/pageSize)),notices};
   }
   const [counts,rows,workload]=await Promise.all([summary(f),query(f,pageSize,(f.page-1)*pageSize),sameWorkload?null:summary(workloadFilters)]);
   return {orders:await Promise.all(rows.map(r=>service.adminDetail(r))),summary:counts,workload:workload||counts,filters:f,page:f.page,pageSize,pages:Math.max(1,Math.ceil(counts.orders/pageSize)),notices};
  },
  async detail(id){if(typeof id!=='string'||!/^NS-[a-zA-Z0-9_-]{1,40}$/.test(id))throw new ShopError(400,'주문번호를 확인해주세요.');return service.adminGet(id);},
  async export(input){
   const f=filters(input,clock);if(!['csv','xlsx'].includes(input.format||'xlsx'))throw new ShopError(400,'파일 형식을 확인해주세요.');
   const rows=await query(f,10001);
   if(rows.length>10000)throw new ShopError(413,'한 번에 1만 건까지 다운로드할 수 있습니다. 조회 기간을 나눠주세요.');
   if(f.ids&&rows.length!==f.ids.length)throw new ShopError(409,'선택 주문이 현재 조회 조건에서 변경되거나 제외되었습니다. 목록을 새로 조회해주세요.');
   const orders=[['주문번호','주문접수일시(KST)','결제확정일시(KST)','PG승인일','결제환경','주문상태','배송상태','구매자','연락처','우편번호','배송주소','확정상품액','배송비','주문총액','확인된원승인액','취소주문의원승인액','부분취소금액','PG거래번호','결제수단','증빙종류','증빙상태','증빙승인번호','소득공제/지출증빙','국세청전송상태','사업자등록번호','상호','증빙이메일','택배사','운송장','환불/정산확인','주문유형','대여시작일','대여종료일','수령방문시간','반납방문시간','실제수령처리일시(KST)','실제반납처리일시(KST)','내부 메모','접수 취소 사유','구매 운영단계','배송완료확인일시(KST)','배송완료확인방식','토스취소확인액','남은결제액','고객구매확정일시(KST)']];
   const lines=[['주문번호','상품ID','상품명','옵션','수량','확정단가','확정상품합계']];
   const docs=[['주문번호','증빙종류','발급상태','승인번호','용도','국세청전송상태','발급확인일시(KST)','재처리횟수','발급확인공급가액','발급확인세액','발급확인합계']];
   const events=[['주문번호','처리일시(KST)','처리주체','처리내역','주문버전']];
   const shipments=[['주문번호','출고ID','출고구분','교환기록ID','출고일시(KST)','운송정보수정일시(KST)','택배사','운송장','상품ID','상품명','옵션','출고수량','출고처리자','운송정보수정자','배송완료확인일시(KST)','배송완료확인방식','배송완료확인자']];
   const cases=[['주문번호','반품교환ID','종류','기록상태(환불상태아님)','대상출고ID','접수일시(KST)','최근처리일시(KST)','상품ID','상품명','옵션','접수수량','접수사유','최근처리메모','회수택배사','회수운송장','교환품남은출고수량','접수처리자','최근처리자']];
   let gross=0,canceled=0;
   for(const row of rows){const r=records(row),{customer:c,doc:d,receipt:p}=r,e=c.evidence||{},live=r.verified&&row.payment_mode==='live',approved=live?row.total:null,fullCanceled=live&&row.state==='CANCELED'?row.total:null;
    gross+=approved||0;canceled+=fullCanceled||0;
    const sums=p?finance.amounts(p,row):null;
    const review=row.state==='PAYMENT_REVIEW'?'부분 취소/결제 상태 확인 필요':row.state==='CANCELED'?(row.payment_key?'취소일과 환불액은 PG 명세 대조':'미결제 접수 취소: 환불 거래 없음'):'PG 수수료/실입금액은 정산명세 대조';
    orders.push([row.id,kstTime(row.created_at),kstTime(r.paidAt),p?.approvalDate||'',row.payment_mode||'미결제',STATE_NAMES[row.state]||row.state,c.rental?(row.fulfillment==='shipped'?'반납 완료':row.fulfillment==='processing'?'대여 중':'수령 예정'):(row.fulfillment==='shipped'?'출고 완료':row.fulfillment==='processing'?'부분 출고':'미출고'),c.name,c.phone,c.postcode,[c.address,c.address_detail].filter(Boolean).join(' '),row.subtotal,row.shipping,row.total,approved,fullCanceled,p?.status==='PARTIAL_CANCELED'?sums?.canceled_amount??null:null,row.payment_key||'',p?.method||'',KIND_NAMES[row.doc_kind||e.kind||'card_receipt'],row.doc_status||'미발급',d?.approval_number||'',d?.purpose==='business'?'지출증빙':d?.purpose==='income'?'소득공제':'',d?.nts_status||'',e.corp_num||'',e.corp_name||'',e.email||'',row.carrier||'',row.tracking||'',review,c.rental?'렌탈':'구매',c.rental?.start_date||'',c.rental?.end_date||'',c.rental?.pickup_time||'',c.rental?.return_time||'',kstTime(c.rental?.actual_pickup_at),kstTime(c.rental?.actual_return_at),c._admin_note?.text||'',c._admin_cancellation?.reason||'',({preparing:'상품 준비 중',ready:'배송 대기',in_transit:'배송 중',delivered:'배송 완료'})[fulfillment.purchaseWorkflow(row,c)?.stage]||'',kstTime(fulfillment.purchaseWorkflow(row,c)?.delivered_at),fulfillment.purchaseWorkflow(row,c)?.delivery_source==='goodsflow'?'택배사 배송 완료 확인':fulfillment.purchaseWorkflow(row,c)?.delivery_source==='manual'?'관리자 수동 확인':'',sums?.canceled_amount??null,sums?.balance_amount??null,kstTime(c._admin_purchase_confirmation?.confirmed_at)]);
    for(const line of JSON.parse(row.lines_json))lines.push([row.id,line.id,line.name,line.option||'',line.quantity,line.unit_price,Number.isSafeInteger(line.unit_price)?line.unit_price*line.quantity:null]);
    const history=fulfillment.shipments(row,c);
    for(const shipment of history)for(const line of shipment.items)shipments.push([row.id,shipment.id,shipment.purpose==='exchange'?'교환품':'주문상품',shipment.case_id||'',kstTime(shipment.created_at),kstTime(shipment.updated_at),shipment.carrier,shipment.tracking,line.id,line.name,line.option,line.quantity,shipment.actor||'',shipment.updated_by||'',kstTime(shipment.delivered_at),shipment.delivered_at?(shipment.delivery_source==='goodsflow'?'택배사 배송 완료 확인':'관리자 수동 확인'):'',shipment.delivery_confirmed_by||'']);
    const caseStates={requested:'접수',approved:'승인',returning:'회수 중',received:'회수 확인',closed:'기록 종결',rejected:'거절'};
    for(const item of fulfillment.adminCases(c._admin_cases||[],history))for(const line of item.items)cases.push([row.id,item.id,item.kind==='exchange'?'교환':'반품',caseStates[item.status]||item.status,item.shipment_id,kstTime(item.created_at),kstTime(item.updated_at),line.id,line.name,line.option,line.quantity,item.reason,item.note||'',item.return_carrier||'',item.return_tracking||'',item.kind==='exchange'?(item.replacement_remaining.find(r=>r.id===line.id&&r.option===line.option)?.quantity||0):null,item.actor,item.updated_by||'']);
    if(row.doc_kind)docs.push([row.id,KIND_NAMES[row.doc_kind],row.doc_status,d?.approval_number||'',d?.purpose||'',d?.nts_status||'',kstTime(row.doc_updated_at),row.doc_attempts,d?.supply_cost??null,d?.tax_amount??null,d?.total_amount??null]);
   }
   // Bound parameters and collect history for exactly the exported order IDs.
   for(let i=0;i<rows.length;i+=100){const ids=rows.slice(i,i+100).map(r=>r.id);
    const data=await db.query(`SELECT order_id,created_at,actor,action,version FROM shop_order_events WHERE order_id IN (${ids.map(()=>'?').join(',')}) ORDER BY created_at,order_id,version`,ids);
    for(const e of data)events.push([e.order_id,kstTime(e.created_at),e.actor,e.action,e.version]);
   }
   const overview=[['나다운 샵 주문·결제 자료','내용'],['조회기간',f.from+' ~ '+f.to],['기간 기준',f.basis==='paid'?'결제확정일':'주문접수일'],['결제환경',f.mode],['주문 건수',rows.length],['실결제 원 승인 누계',gross],['전체 취소 주문의 원 승인액',canceled],['생성일시(KST)',kstTime(clock())],...notices.map(t=>['자료 기준',t])];
   const filename='nadaun-orders-'+f.from+'_'+f.to+'.'+(input.format||'xlsx');
   if(input.format==='csv')return {filename,type:'text/csv; charset=utf-8',body:Buffer.from(csv(orders))};
   const ExcelJS=require('exceljs'),workbook=new ExcelJS.Workbook();workbook.creator='NADAUN SHOP';workbook.created=new Date(clock());
   for(const [name,data] of [['안내와합계',overview],['주문결제',orders],['상품',lines],['증빙',docs],['처리이력',events],['출고내역',shipments],['반품교환',cases]]){const sheet=workbook.addWorksheet(name);sheet.addRows(data);sheet.views=[{state:'frozen',ySplit:1}];sheet.getRow(1).font={bold:true,color:{argb:'FFFFFFFF'}};sheet.getRow(1).fill={type:'pattern',pattern:'solid',fgColor:{argb:'FF686247'}};sheet.columns.forEach((col,i)=>{col.width=i===0?42:24;});if(data.length>1&&name!=='안내와합계')sheet.autoFilter={from:{row:1,column:1},to:{row:1,column:data[0].length}};}
   return {filename,type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',body:Buffer.from(await workbook.xlsx.writeBuffer())};
  }
 };
}
module.exports={adminService,filters,where,csv,kstTime};
