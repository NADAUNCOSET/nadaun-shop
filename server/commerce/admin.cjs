'use strict';
const {ShopError,protect}=require('./security.cjs');
const STATES=['REQUESTED','APPROVED','PAYMENT_PENDING','CONFIRMING','PAID','PAYMENT_REVIEW','CANCELED'];
const STATE_NAMES={REQUESTED:'재고·납기 확인 중',APPROVED:'결제 가능',PAYMENT_PENDING:'결제 진행 중',CONFIRMING:'결제 결과 확인 중',PAID:'결제 완료',PAYMENT_REVIEW:'결제 확인 필요',CANCELED:'취소 완료'};
const KIND_NAMES={card_receipt:'카드 매출전표',cash_receipt:'현금영수증',tax_invoice:'전자세금계산서'};
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
 const basis=input.basis||'created',mode=input.mode||'operational',state=input.state||'',fulfillment=input.fulfillment||'',document=input.document||'',search=(input.search||'').trim();
 if(!['created','paid'].includes(basis)||!['operational','live','test','all'].includes(mode)||state&&!STATES.includes(state)||fulfillment&&!['unfulfilled','processing','shipped'].includes(fulfillment)||document&&!['queued','processing','issued','retry','review','voided','missing'].includes(document)||search.length>80||/[\x00-\x1f]/.test(search))throw new ShopError(400,'조회 조건을 확인해주세요.');
 const page=Number(input.page||1);if(!Number.isSafeInteger(page)||page<1||page>100000)throw new ShopError(400,'페이지를 확인해주세요.');
 return {from,to,start,end,basis,mode,state,fulfillment,document,search,page};
}
function where(f){
 const time=f.basis==='paid'?"COALESCE(o.paid_at,(SELECT e.created_at FROM shop_order_events e WHERE e.order_id=o.id AND e.action='payment_done' LIMIT 1))":'o.created_at';
 const terms=[time+'>=?',time+'<?'],params=[f.start,f.end];
 if(f.mode==='operational')terms.push("(o.payment_mode IS NULL OR o.payment_mode='live')");
 else if(f.mode!=='all'){terms.push('o.payment_mode=?');params.push(f.mode);}
 for(const [field,value] of [['state',f.state],['fulfillment',f.fulfillment]])if(value){terms.push('o.'+field+'=?');params.push(value);}
 if(f.document==='missing')terms.push('d.order_id IS NULL');else if(f.document){terms.push('d.status=?');params.push(f.document);}
 if(f.search){terms.push('(instr(o.id,?)>0 OR instr(COALESCE(o.payment_key,\'\'),?)>0)');params.push(f.search,f.search);}
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
 function records(row){
  const customer=cipher.decrypt(row.customer_cipher),doc=row.doc_result?cipher.decrypt(row.doc_result):null;
  let receipt=null;if(row.payment_receipt_cipher)receipt=cipher.decrypt(row.payment_receipt_cipher);
  const verified=!!receipt&&receipt.provider==='inicis'&&receipt.orderId===row.id&&receipt.paymentKey===row.payment_key&&receipt.totalAmount===row.total&&receipt.currency==='KRW'&&receipt.status==='DONE';
  const paidAt=row.paid_at||row.confirmed_at||null;
  return {row,customer,doc,receipt,verified,paidAt};
 }
 async function query(f,limit,offsetRows=0){
  const w=where(f);
  return db.query(`SELECT o.*,d.kind AS doc_kind,d.status AS doc_status,d.result_cipher AS doc_result,
   d.attempts AS doc_attempts,d.updated_at AS doc_updated_at,
   (SELECT e.created_at FROM shop_order_events e WHERE e.order_id=o.id AND e.action='payment_done' LIMIT 1) AS confirmed_at
   FROM shop_orders o LEFT JOIN shop_documents d ON d.order_id=o.id WHERE ${w.sql}
   ORDER BY o.created_at DESC,o.id DESC LIMIT ? OFFSET ?`,[...w.params,limit,offsetRows]);
 }
 async function summary(f){
  const w=where(f);
  const rows=await db.query(`SELECT COUNT(*) AS orders,
   SUM(CASE WHEN o.state='REQUESTED' THEN 1 ELSE 0 END) AS requested,
   SUM(CASE WHEN o.state='PAID' AND o.fulfillment!='shipped' AND o.payment_mode='live' THEN 1 ELSE 0 END) AS toShip,
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
  '이 자료는 주문·결제·발급 처리 내역입니다. 세무 신고 및 이니시스 정산명세를 대체하지 않습니다.',
  '필터에 해당하는 전체 주문을 다운로드합니다. 화면의 현재 페이지에 한정되지 않습니다.'
 ];
 return {
  async list(input){const f=filters(input,clock),counts=await summary(f),pageSize=25,rows=await query(f,pageSize,(f.page-1)*pageSize);return {orders:await Promise.all(rows.map(r=>service.adminDetail(r))),summary:counts,filters:f,page:f.page,pageSize,pages:Math.max(1,Math.ceil(counts.orders/pageSize)),notices};},
  async detail(id){if(typeof id!=='string'||!/^NS-[a-zA-Z0-9_-]{1,40}$/.test(id))throw new ShopError(400,'주문번호를 확인해주세요.');return service.adminGet(id);},
  async export(input){
   const f=filters(input,clock);if(!['csv','xlsx'].includes(input.format||'xlsx'))throw new ShopError(400,'파일 형식을 확인해주세요.');
   const initial=await summary(f);if(initial.orders>10000)throw new ShopError(413,'한 번에 1만 건까지 다운로드할 수 있습니다. 조회 기간을 나눠주세요.');
   // Use a stable keyset cursor. New orders above this snapshot cannot shift page offsets.
   const w=where(f),rows=[];let cursor=null;
   while(true){const params=[...w.params],clause=cursor?' AND (o.created_at<? OR (o.created_at=? AND o.id<?))':'';
    if(cursor)params.push(cursor.created_at,cursor.created_at,cursor.id);
    const batch=await db.query(`SELECT o.*,d.kind AS doc_kind,d.status AS doc_status,d.result_cipher AS doc_result,d.attempts AS doc_attempts,d.updated_at AS doc_updated_at,
     (SELECT e.created_at FROM shop_order_events e WHERE e.order_id=o.id AND e.action='payment_done' LIMIT 1) AS confirmed_at
     FROM shop_orders o LEFT JOIN shop_documents d ON d.order_id=o.id WHERE ${w.sql}${clause} ORDER BY o.created_at DESC,o.id DESC LIMIT 500`,params);
    rows.push(...batch);if(rows.length>10000)throw new ShopError(413,'자료 건수가 증가했습니다. 기간을 나눠 다운로드해주세요.');if(batch.length<500)break;cursor=batch.at(-1);
   }
   const orders=[['주문번호','주문접수일시(KST)','결제확정일시(KST)','PG승인일','결제환경','주문상태','배송상태','구매자','연락처','우편번호','배송주소','확정상품액','배송비','주문총액','확인된원승인액','취소주문의원승인액','부분취소금액','PG거래번호','결제수단','증빙종류','증빙상태','증빙승인번호','소득공제/지출증빙','국세청전송상태','사업자등록번호','상호','증빙이메일','택배사','운송장','환불/정산확인','주문유형','대여시작일','대여종료일','수령방문시간','반납방문시간','실제수령처리일시(KST)','실제반납처리일시(KST)']];
   const lines=[['주문번호','상품ID','상품명','옵션','수량','확정단가','확정상품합계']];
   const docs=[['주문번호','증빙종류','발급상태','승인번호','용도','국세청전송상태','발급확인일시(KST)','재처리횟수','발급확인공급가액','발급확인세액','발급확인합계']];
   const events=[['주문번호','처리일시(KST)','처리주체','처리내역','주문버전']];
   let gross=0,canceled=0;
   for(const row of rows){const r=records(row),{customer:c,doc:d,receipt:p}=r,e=c.evidence||{},live=r.verified&&row.payment_mode==='live',approved=live?row.total:null,fullCanceled=live&&row.state==='CANCELED'?row.total:null;
    gross+=approved||0;canceled+=fullCanceled||0;
    const review=row.state==='PAYMENT_REVIEW'?'부분 취소/결제 상태 확인 필요':row.state==='CANCELED'?'취소일과 환불액은 PG 명세 대조':'PG 수수료/실입금액은 정산명세 대조';
    orders.push([row.id,kstTime(row.created_at),kstTime(r.paidAt),p?.approvalDate||'',row.payment_mode||'미결제',STATE_NAMES[row.state]||row.state,c.rental?(row.fulfillment==='shipped'?'반납 완료':row.fulfillment==='processing'?'대여 중':'수령 예정'):(row.fulfillment==='shipped'?'출고 완료':'미출고'),c.name,c.phone,c.postcode,[c.address,c.address_detail].filter(Boolean).join(' '),row.subtotal,row.shipping,row.total,approved,fullCanceled,null,row.payment_key||'',p?.method||'',KIND_NAMES[row.doc_kind||e.kind||'card_receipt'],row.doc_status||'미발급',d?.approval_number||'',d?.purpose==='business'?'지출증빙':d?.purpose==='income'?'소득공제':'',d?.nts_status||'',e.corp_num||'',e.corp_name||'',e.email||'',row.carrier||'',row.tracking||'',review,c.rental?'렌탈':'구매',c.rental?.start_date||'',c.rental?.end_date||'',c.rental?.pickup_time||'',c.rental?.return_time||'',kstTime(c.rental?.actual_pickup_at),kstTime(c.rental?.actual_return_at)]);
    for(const line of JSON.parse(row.lines_json))lines.push([row.id,line.id,line.name,line.option||'',line.quantity,line.unit_price,Number.isSafeInteger(line.unit_price)?line.unit_price*line.quantity:null]);
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
   for(const [name,data] of [['안내와합계',overview],['주문결제',orders],['상품',lines],['증빙',docs],['처리이력',events]]){const sheet=workbook.addWorksheet(name);sheet.addRows(data);sheet.views=[{state:'frozen',ySplit:1}];sheet.getRow(1).font={bold:true,color:{argb:'FFFFFFFF'}};sheet.getRow(1).fill={type:'pattern',pattern:'solid',fgColor:{argb:'FF686247'}};sheet.columns.forEach((col,i)=>{col.width=i===0?42:24;});if(data.length>1&&name!=='안내와합계')sheet.autoFilter={from:{row:1,column:1},to:{row:1,column:data[0].length}};}
   return {filename,type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',body:Buffer.from(await workbook.xlsx.writeBuffer())};
  }
 };
}
module.exports={adminService,filters,where,csv,kstTime};
