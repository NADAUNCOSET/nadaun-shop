'use strict';

const crypto=require('node:crypto');
const {ShopError,protect,adminEmail}=require('./security.cjs');
const {quoteCatalog}=require('./pricing.cjs');
const {rentalSchedule,rentalQuote}=require('./rental.cjs');

const NOTICE='관리자 내부 견적 초안입니다. 검토 완료는 상품·가격·일정 입력의 검증이며 재고 예약, 주문 접수 또는 결제 확정이 아닙니다. 고객에게 전송되지 않습니다.';
const STATES=new Set(['draft','reviewed','voided']);
const KINDS=new Set(['purchase','rental']);
const DRAFT_ID=/^ND-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const uuid=()=>crypto.randomUUID();
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=value=>value===null?'금액 미확정':Number(value).toLocaleString('ko-KR')+'원';

// This is an internal service, not an authentication endpoint. The HTTP adapter
// must pass its verified admin-session subject, never an actor from request JSON.
function requireActor(actor){
 if(typeof actor!=='string'||!actor.trim()||actor.length>254||/[\x00-\x1f\x7f]/.test(actor))throw new ShopError(401,'관리자 로그인이 필요합니다.');
 return actor.trim();
}
function object(value){if(!value||typeof value!=='object'||Array.isArray(value))throw new ShopError(400,'견적 초안 내용을 확인해주세요.');return value;}
function privateText(value,max,label,required=false){
 if(typeof value!=='string'||value.length>max||/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(value))throw new ShopError(400,label+'을 확인해주세요.');
 const text=value.trim();if(required&&text.length<2)throw new ShopError(400,label+'을 2자 이상 입력해주세요.');return text;
}
function contact(raw){
 object(raw);
 const value={};
 for(const [key,min,max] of [['name',2,60],['phone',9,20]]){
  const text=typeof raw[key]==='string'?raw[key].trim():'';
  if(text.length<min||text.length>max||/[\x00-\x1f\x7f<>]/.test(text))throw new ShopError(400,'견적 고객의 이름과 연락처를 확인해주세요.');
  value[key]=text;
 }
 if(!/^0[\d -]{8,19}$/.test(value.phone))throw new ShopError(400,'견적 고객의 연락처를 확인해주세요.');
 if(raw.email!==undefined&&raw.email!==''){
  const email=adminEmail(raw.email);if(!email)throw new ShopError(400,'견적 고객의 이메일을 확인해주세요.');value.email=email;
 }
 for(const [key,max] of [['postcode',5],['address',160],['address_detail',100]]){
  if(raw[key]===undefined||raw[key]==='')continue;
  if(typeof raw[key]!=='string'||raw[key].trim().length>max||/[\x00-\x1f\x7f<>]/.test(raw[key]))throw new ShopError(400,'견적의 배송 주소를 확인해주세요.');
  const text=raw[key].trim();if(text)value[key]=text;
 }
 if(value.postcode&&!/^\d{5}$/.test(value.postcode))throw new ShopError(400,'견적의 우편번호를 확인해주세요.');
 // Administrator-entered contact details are not customer consent or ownership.
 return value;
}
function versionMatches(row,input){
 if(!Number.isSafeInteger(input.version)||input.version<0||input.version!==row.version)throw new ShopError(409,'견적 초안이 변경되었습니다. 새로고침 후 다시 확인해주세요.');
 if(row.state==='voided')throw new ShopError(409,'취소한 견적 초안은 수정하거나 검토할 수 없습니다. 새 초안을 작성해주세요.');
}

function adminDraftService({db,catalog,detail,dataKey,clock=()=>Date.now()}){
 const cipher=protect(dataKey);
 const fingerprint=value=>crypto.createHmac('sha256',Buffer.from(dataKey,'hex')).update(JSON.stringify(value)).digest('hex');

 function validate(input){
  object(input);
  if(!KINDS.has(input.kind))throw new ShopError(400,'구매 또는 렌탈 견적을 선택해주세요.');
  const customer=contact(input.customer),note=privateText(input.note??'',2000,'내부 메모');
  const rental=input.kind==='rental'?rentalSchedule(input.rental,clock):null;
  if(input.kind==='purchase'&&(input.rental!=null||input.rental_prices!=null))throw new ShopError(400,'구매 견적에는 렌탈 일정이나 기간 단가를 입력할 수 없습니다.');
  const quote=rental?rentalQuote(catalog,detail,input.items,input.rental_prices??null,clock):quoteCatalog(catalog,detail,input.items,clock);
  return {kind:input.kind,customer,note,rental,...quote};
 }
 function dto(row,summary=false){
  const privateData=cipher.decrypt(row.private_cipher),items=JSON.parse(row.lines_json);
  const result={
   id:row.id,kind:row.kind,state:row.state,version:row.version,
   customer:summary?{name:privateData.customer.name}:privateData.customer,
   items,subtotal:row.subtotal,shipping:row.shipping,total:row.total,
   rental:privateData.rental||null,created_at:row.created_at,updated_at:row.updated_at,reviewed_at:row.reviewed_at,
   is_actual_order:false,payment_available:false,inventory_reserved:false,notice:NOTICE
  };
  if(!summary){
   result.note=privateData.note;
   result.void_reason=privateData.void_reason||null;
   result.created_by=row.created_by;result.updated_by=row.updated_by;
  }
  return result;
 }
 async function load(id){
  if(typeof id!=='string'||!DRAFT_ID.test(id))throw new ShopError(400,'견적 초안 번호를 확인해주세요.');
  const row=(await db.query('SELECT * FROM shop_admin_drafts WHERE id=?',[id]))[0];
  if(!row)throw new ShopError(404,'견적 초안을 찾을 수 없습니다.');return row;
 }
 async function patch(row,fields,actor,action){
  const allowed=new Set(['state','kind','private_cipher','lines_json','subtotal','shipping','total','reviewed_at']);
  const keys=Object.keys(fields);if(!keys.length||keys.some(key=>!allowed.has(key)))throw Error('Invalid internal draft update');
  const now=clock(),version=row.version+1;
  const result=await db.batch([
   {sql:`UPDATE shop_admin_drafts SET ${keys.map(key=>key+'=?').join(',')},updated_at=?,updated_by=?,version=version+1 WHERE id=? AND version=? AND state!='voided' RETURNING *`,params:[...keys.map(key=>fields[key]),now,actor,row.id,row.version]},
   {sql:'INSERT INTO shop_admin_draft_events(id,draft_id,actor,action,created_at,version) SELECT ?,?,?,?,?,? WHERE changes()=1',params:[uuid(),row.id,actor,action,now,version]}
  ]);
  if(!result[0]?.length)throw new ShopError(409,'견적 초안이 변경되었습니다. 새로고침 후 다시 확인해주세요.');return result[0][0];
 }
 function snapshot(value){return {private_cipher:cipher.encrypt({customer:value.customer,note:value.note,rental:value.rental}),kind:value.kind,lines_json:JSON.stringify(value.lines),subtotal:value.subtotal,shipping:value.shipping,total:value.total};}
 function freshQuote(row){
  const saved=cipher.decrypt(row.private_cipher),lines=JSON.parse(row.lines_json);
  const value=validate({kind:row.kind,customer:saved.customer,note:saved.note,rental:saved.rental,
   items:lines.map(({id,option,quantity})=>({id,option,quantity})),
   ...(row.kind==='rental'?{rental_prices:lines.every(line=>line.unit_price!==null)?lines.map(({id,option,unit_price})=>({id,option,unit_price})):null}:{})});
  const comparable=items=>items.map(({id,name,option,quantity,unit_price,shipping_class})=>({id,name,option,quantity,unit_price,shipping_class}));
  if(JSON.stringify(comparable(value.lines))!==JSON.stringify(comparable(lines))||value.subtotal!==row.subtotal||value.shipping!==row.shipping||value.total!==row.total)throw new ShopError(409,'상품 또는 견적 금액이 변경되었습니다. 초안을 다시 저장한 뒤 검토해주세요.');
  return value;
 }
 return {
  async products(input={},actor){
   requireActor(actor);object(input);
   if(!KINDS.has(input.kind))throw new ShopError(400,'구매 또는 렌탈 상품을 선택해주세요.');
   if(input.q!==undefined&&(typeof input.q!=='string'||input.q.length>100||/[\x00-\x1f\x7f]/.test(input.q)))throw new ShopError(400,'상품 검색어를 확인해주세요.');
   const at=Date.parse(catalog.meta.synced_at);
   if(!Number.isFinite(at)||clock()-at>48*3600000||at>clock()+60000)throw new ShopError(503,'최신 상품 정보를 확인하고 있습니다. 잠시 후 다시 시도해주세요.');
   const tokens=(input.q||'').normalize('NFKC').toLowerCase().trim().split(/\s+/).filter(Boolean);
   const matches=catalog.products.filter(p=>p.kind===input.kind&&p.status!=='soldout'&&p.release_status!=='coming_soon'&&tokens.every(token=>(p.id+' '+p.name).normalize('NFKC').toLowerCase().includes(token)));
   // Bound detail-shard reads to the returned 20 products. The total describes
   // catalog matches; unavailable option configurations remain visible/disabled.
   const products=matches.slice(0,20).map(p=>{
    const d=detail(p),rental=p.kind==='rental',raw=rental?(d.rental?.rates||[]).map(rate=>({name:rate.label,additional_price:0})):(d.options||[]);
    const price=rental?null:(p.offers.some(offer=>['smartstore','imweb'].includes(offer.source))?(p.sale_price??p.price):p.price);
    const options=(raw.length?raw:[{name:'',additional_price:0}]).slice(0,100).map(option=>({
     name:option.name,additional_price:rental?0:(option.additional_price??0),
     disabled:typeof option.name!=='string'||option.name.length>300||raw.filter(other=>other.name===option.name).length>1||!!(option.disabled||option.soldout||option.displayed===false||['soldout','unknown'].includes(option.supplier_status))||!Number.isSafeInteger(option.additional_price??0)||(!rental&&price!==null&&(!Number.isSafeInteger(price+(option.additional_price??0))||price+(option.additional_price??0)<1||price+(option.additional_price??0)>100000000))
    }));
    const disabled=(!rental&&!!d.options_require_confirmation)||options.every(option=>option.disabled);
    return {id:p.id,name:p.name,kind:p.kind,status:p.status,price,options,disabled,...(disabled?{notice:'상품 옵션과 판매 가능 여부를 상담으로 확인해야 합니다.'}:{}),...(raw.length>100?{notice:'옵션이 많습니다. 상품 상세에서 전체 구성을 확인해주세요.'}:{})};
   });
   return {products,total:matches.length};
  },
  async list(input={},actor){
   requireActor(actor);object(input);
   const page=Number(input.page??1);if(!Number.isSafeInteger(page)||page<1||page>100000)throw new ShopError(400,'견적 목록 페이지를 확인해주세요.');
   const where=[],params=[];
   for(const [key,allowed] of [['state',STATES],['kind',KINDS]])if(input[key]){if(!allowed.has(input[key]))throw new ShopError(400,'견적 목록 조건을 확인해주세요.');where.push(key+'=?');params.push(input[key]);}
   const condition=where.length?' WHERE '+where.join(' AND '):'',pageSize=25;
   const [counts,rows]=await Promise.all([
    db.query('SELECT COUNT(*) AS total FROM shop_admin_drafts'+condition,params),
    db.query('SELECT * FROM shop_admin_drafts'+condition+' ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?',[...params,pageSize,(page-1)*pageSize])
   ]);
   const total=Number(counts[0]?.total)||0;
   return {drafts:rows.map(row=>dto(row,true)),total,page,pageSize,pages:Math.max(1,Math.ceil(total/pageSize)),is_actual_order:false,payment_available:false};
  },
  async get(id,actor){requireActor(actor);return dto(await load(id));},
  async create(input,actor){
   actor=requireActor(actor);const value=validate(input),now=clock();
   if(input.request_key!==undefined&&(typeof input.request_key!=='string'||!/^[a-zA-Z0-9_-]{16,100}$/.test(input.request_key)))throw new ShopError(400,'견적 저장 요청 번호를 확인해주세요.');
   const requestKey=input.request_key??uuid(),requestFingerprint=fingerprint(value);
   const row={id:'ND-'+uuid(),request_key:requestKey,request_fingerprint:requestFingerprint,state:'draft',...snapshot(value),created_by:actor,updated_by:actor,created_at:now,updated_at:now,reviewed_at:null,version:0};
   const keys=Object.keys(row);
   const result=await db.batch([
    {sql:`INSERT INTO shop_admin_drafts(${keys.join(',')}) VALUES(${keys.map(()=>'?').join(',')}) ON CONFLICT(created_by,request_key) DO NOTHING`,params:keys.map(key=>row[key])},
    {sql:'INSERT INTO shop_admin_draft_events(id,draft_id,actor,action,created_at,version) SELECT ?,?,?,?,?,0 WHERE changes()=1',params:[uuid(),row.id,actor,'draft_created',now]},
    {sql:'SELECT * FROM shop_admin_drafts WHERE created_by=? AND request_key=?',params:[actor,requestKey]}
   ]);
   const saved=result[2]?.[0];
   if(!saved||saved.request_fingerprint!==requestFingerprint)throw new ShopError(409,'같은 저장 요청 번호의 견적 내용이 달라졌습니다. 새 초안으로 저장해주세요.');
   return dto(saved);
  },
  async update(id,input,actor){
   actor=requireActor(actor);object(input);const row=await load(id);versionMatches(row,input);
   const value=validate(input);
   return dto(await patch(row,{...snapshot(value),state:'draft',reviewed_at:null},actor,'draft_updated'));
  },
  async review(id,input,actor){
   actor=requireActor(actor);object(input);const row=await load(id);versionMatches(row,input);
   if(row.state!=='draft')throw new ShopError(409,'이미 검토한 견적입니다. 수정 사항이 있다면 초안을 다시 저장해주세요.');
   const value=freshQuote(row);
   if(value.total===null)throw new ShopError(409,'상품별 금액이 미확정입니다. 렌탈은 전체 대여 기간 단가를 입력하고, 구매는 공개 가격을 확인한 뒤 초안을 다시 저장해주세요.');
   return dto(await patch(row,{...snapshot(value),state:'reviewed',reviewed_at:clock()},actor,'draft_reviewed'));
  },
  async void(id,input,actor){
   actor=requireActor(actor);object(input);const row=await load(id);versionMatches(row,input);
   const privateData=cipher.decrypt(row.private_cipher);privateData.void_reason=privateText(input.reason,1000,'견적 취소 사유',true);
   return dto(await patch(row,{state:'voided',private_cipher:cipher.encrypt(privateData)},actor,'draft_voided'));
  },
  async events(id,actor){requireActor(actor);await load(id);return db.query('SELECT actor,action,created_at,version FROM shop_admin_draft_events WHERE draft_id=? ORDER BY version',[id]);},
  async quote(id,actor){
   requireActor(actor);const row=await load(id);
   if(row.state==='voided')throw new ShopError(409,'취소한 견적 초안은 출력할 수 없습니다.');
   const value=dto(row),date=ms=>new Date(ms).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'});
   const title=value.state==='reviewed'?'검토 견적':'견적 초안';
   const body=`<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer"><title>${title} · ${esc(value.id)}</title><style>body{font:15px/1.6 system-ui,sans-serif;color:#171717;margin:40px;max-width:1000px}h1{font-size:28px}table{width:100%;border-collapse:collapse;margin:24px 0}th,td{padding:10px;border-bottom:1px solid #ccc;text-align:left}td.num{text-align:right}aside{padding:16px;background:#f3f3f3}dl{display:grid;grid-template-columns:120px 1fr}dt,dd{margin:4px 0}footer{margin-top:24px;font-size:12px}@media print{body{margin:15mm;font-size:12px}tr{break-inside:avoid}}</style></head><body><header><p>나다운 스페이스</p><h1>${title}</h1><p>${esc(value.id)} · 버전 ${value.version}</p></header><aside>${esc(NOTICE)}</aside><dl><dt>고객</dt><dd>${esc(value.customer.name)}</dd><dt>연락처</dt><dd>${esc(value.customer.phone)}</dd>${value.customer.email?`<dt>이메일</dt><dd>${esc(value.customer.email)}</dd>`:''}${value.customer.address?`<dt>배송지</dt><dd>${esc([value.customer.postcode,value.customer.address,value.customer.address_detail].filter(Boolean).join(' '))}</dd>`:''}<dt>견적 유형</dt><dd>${value.kind==='rental'?'렌탈 · 단가는 전체 대여 기간 기준':'상품 구매'}</dd>${value.rental?`<dt>수령 예정</dt><dd>${esc(value.rental.start_date+' '+value.rental.pickup_time)}</dd><dt>반납 예정</dt><dd>${esc(value.rental.end_date+' '+value.rental.return_time)}</dd>`:''}</dl><table><thead><tr><th>상품·구성</th><th>수량</th><th>단가</th><th>금액</th></tr></thead><tbody>${value.items.map(item=>`<tr><td>${esc(item.name)}${item.option?'<br>'+esc(item.option):''}</td><td class="num">${item.quantity}</td><td class="num">${money(item.unit_price)}</td><td class="num">${money(item.unit_price===null?null:item.unit_price*item.quantity)}</td></tr>`).join('')}</tbody></table><dl><dt>상품 금액</dt><dd>${money(value.subtotal)}</dd><dt>${value.kind==='rental'?'방문 수령':'배송비'}</dt><dd>${money(value.shipping)}</dd><dt>견적 합계</dt><dd><strong>${money(value.total)}</strong></dd></dl><p>이 문서는 견적이며 주문서, 결제 영수증 또는 세금계산서가 아닙니다. 실제 재고·납기·대여 가능 여부는 별도로 확인합니다.</p><footer>초안 수정: ${esc(date(value.updated_at))}${value.reviewed_at?' · 입력 검토: '+esc(date(value.reviewed_at)):''}<br>출력: ${esc(date(clock()))} (한국 시간)</footer></body></html>`;
   return {body:body.replace('<aside>','<aside><strong>저장 당시의 견적입니다. 현재 가격·재고·일정은 재검토가 필요합니다.</strong><br>'),type:'text/html; charset=utf-8',filename:'nadaun-quote-'+value.id+'.html'};
  }
 };
}

module.exports={adminDraftService};
