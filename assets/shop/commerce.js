const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>Number.isSafeInteger(v)?v.toLocaleString('ko-KR')+'원':'금액 확인 필요';
const states={REQUESTED:'재고·납기 확인 중',APPROVED:'결제 가능',PAYMENT_PENDING:'결제 진행 중',CONFIRMING:'결제 결과 확인 중',PAID:'결제 완료',PAYMENT_REVIEW:'결제 확인 필요',CANCELED:'취소 완료'};
const mode=document.body.dataset.mode;
const main=document.querySelector('#main');
async function api(action,body,headers={}){
 const response=await fetch('/api/orders?action='+encodeURIComponent(action),{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:{...(body===undefined?{}:{'Content-Type':'application/json'}),...headers},...(body===undefined?{}:{body:JSON.stringify(body)})});
 let value;try{value=await response.json();}catch{throw Error('주문 서비스 응답을 확인하지 못했습니다. 잠시 후 다시 확인해주세요.');}
 if(!response.ok){const error=Error(value.error||'주문을 처리하지 못했습니다.');error.status=response.status;throw error;}return value;
}
let configRequest;
let checkoutPaymentOpen=true;
let commerceTesting=false;
const config=()=>configRequest||(configRequest=api('config'));
function message(target,text){target.textContent=text;target.hidden=!text;}
const notice='<p class="commerce-note"><a href="/account.html">회원 로그인</a> 후 주문하면 다른 기기에서도 내 주문을 확인할 수 있습니다. 비회원 주문은 접수한 브라우저에서 조회할 수 있습니다.</p>';
const blocked='<div class="commerce-empty"><h2>온라인 주문 오픈 준비 중입니다.</h2><p>상품 구매와 견적은 상담으로 안내해드립니다.</p><a class="button-primary" href="https://pf.kakao.com/_pyNxnxb/chat" target="_blank" rel="noopener">카카오톡 구매 상담 ↗</a></div>';
function checkoutItems(){
 const rows=JSON.parse(localStorage.getItem('nadaun-shop-cart-v1')||'[]');if(!Array.isArray(rows))throw Error('장바구니 내용을 다시 확인해주세요.');
 return rows.filter(row=>row&&row.selected!==false).map(({id,option,quantity})=>({id,option,quantity}));
}
async function mountCheckout(){
 const services=main.querySelector('.checkout-services');if(!services||main.querySelector('#delivery-form'))return;
 let ready;try{ready=await config();}catch{return;}if(!services.isConnected||main.querySelector('#delivery-form'))return;
 if(!ready.ordersEnabled)return;
 const form=document.createElement('form');form.id='delivery-form';form.className='commerce-form';
 form.innerHTML='<div class="section-index">DELIVERY</div><h2>받으실 곳</h2><p>접수 후 재고·납기를 확인하면 주문 조회에서 확정 금액으로 결제할 수 있습니다.</p><div class="commerce-fields">'+[
  ['name','받는 분','text','name',60],['phone','연락처','tel','tel',20],['postcode','우편번호','text','postal-code',5],['address','주소','text','address-line1',160],['address_detail','상세 주소','text','address-line2',100]
 ].map(([key,label,type,autocomplete,max])=>`<label>${label}<input name="${key}" type="${type}" autocomplete="${autocomplete}" maxlength="${max}" required ${key==='postcode'?'inputmode="numeric" pattern="[0-9]{5}"':''}></label>`).join('')+'</div>'+evidenceForm(ready.taxInvoiceEnabled)+'<label class="commerce-check"><input type="checkbox" name="consent" required><span>주문·배송 및 선택한 증빙 발급에 필요한 이름, 연락처, 주소와 사업자 정보·이메일의 수집·이용에 동의합니다. <a href="/privacy.html" target="_blank" rel="noopener">처리 항목과 보유기간 확인 ↗</a></span></label><p class="commerce-feedback" role="status" hidden></p><button type="submit" class="button-primary">주문 접수하기 →</button>'+notice;
 services.before(form);
 const evidenceSelect=form.querySelector('[name=evidence_kind]');
 evidenceSelect.onchange=()=>{const tax=form.querySelector('[data-tax-fields]'),active=evidenceSelect.value==='tax_invoice';tax.hidden=!active;tax.querySelectorAll('input').forEach(input=>{input.disabled=!active;input.required=active;});};evidenceSelect.onchange();
 const state=main.querySelector('.summary-state');if(state)state.textContent='재고·납기 확인 후 결제';
 const contact=main.querySelector('.order-summary .button-primary');if(contact){contact.href='#delivery-form';contact.firstChild.textContent='배송 정보 입력하기 ';}
 const note=main.querySelector('.contact-note');if(note)note.textContent='주문 접수 후 주문 조회에서 진행 상태를 확인해주세요.';
 const step=main.querySelector('.selection-steps li:last-child');if(step)step.innerHTML='<span>03</span>접수 · 결제';
 const key=crypto.randomUUID();let sentPayload;
 form.addEventListener('submit',async event=>{
  event.preventDefault();const button=form.querySelector('button'),feedback=form.querySelector('.commerce-feedback');button.disabled=true;message(feedback,'주문을 접수하고 있습니다.');
  try{
   if(!sentPayload){const fields=new FormData(form),items=checkoutItems();sentPayload={customer:Object.fromEntries(['name','phone','postcode','address','address_detail'].map(k=>[k,fields.get(k)])),items};sentPayload.customer.consent=fields.has('consent');sentPayload.evidence={kind:fields.get('evidence_kind')};if(sentPayload.evidence.kind==='tax_invoice')for(const k of ['corp_num','corp_name','ceo_name','address','biz_type','biz_class','email'])sentPayload.evidence[k]=fields.get('tax_'+k);}
   form.querySelectorAll('input,select').forEach(input=>input.disabled=true);
   await api('session',{});const {order}=await api('create',sentPayload,{'Idempotency-Key':key});location.assign('/orders.html#'+encodeURIComponent(order.id));
  }catch(error){message(feedback,error.message);if(error.status&&error.status<500&&error.status!==429){sentPayload=undefined;form.querySelectorAll('input,select').forEach(input=>input.disabled=false);evidenceSelect.onchange();}else{message(feedback,error.message+' 입력한 내용 그대로 다시 접수 버튼을 눌러주세요.');}button.disabled=false;}
 });
}
function evidenceForm(taxEnabled){
 return '<fieldset class="commerce-evidence"><legend>결제 방법과 증빙</legend><label>증빙 선택<select name="evidence_kind"><option value="card_receipt">카드 결제 · 카드 매출전표</option><option value="cash_receipt">계좌이체 · 현금영수증 (소득공제 / 지출증빙)</option>'+(taxEnabled?'<option value="tax_invoice">계좌이체 · 전자세금계산서</option>':'')+'</select></label><p class="commerce-note">현금영수증은 토스페이먼츠 결제창에서 소득공제 또는 사업자 지출증빙을 선택하고 발급 정보를 입력해주세요. 세금계산서를 선택하면 현금영수증은 함께 발급하지 않습니다.</p>'+(taxEnabled?'':'<p class="commerce-note">전자세금계산서 발급 연결을 준비 중입니다. 필요한 경우 구매 전 상담해주세요.</p>')+'<div class="commerce-fields" data-tax-fields hidden>'+[
  ['corp_num','사업자등록번호 (숫자 10자리)','text',10],['corp_name','상호','text',200],['ceo_name','대표자명','text',100],['address','사업장 주소','text',300],['biz_type','업태','text',100],['biz_class','종목','text',100],['email','세금계산서 수신 이메일','email',100]
 ].map(([key,label,type,max])=>`<label>${label}<input name="tax_${key}" type="${type}" maxlength="${max}" disabled ${key==='corp_num'?'inputmode="numeric" pattern="[0-9]{10}"':''}></label>`).join('')+'</div></fieldset>';
}
function giftInfo(order){
 if(!order.gift)return '';
 return '<section class="commerce-gift-info"><h3>기프트 제작 요청</h3><dl>'+[['상품번호',order.gift.product_id],['색상·사양',order.gift.variant],['인쇄',order.gift.printing],['포장',order.gift.packaging],['희망 수령일',order.gift.requested_date],['추가 요청',order.gift.notes]].filter(([,v])=>v).map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')+'</dl><p>확정 단가는 인쇄·포장·부가세 포함이며 배송비는 별도 표시됩니다.</p></section>';
}
async function mountGiftOrder(){
 const target=main.querySelector('[data-gift-order]');if(!target||target.dataset.giftSoldout==='true')return;
 let ready;try{ready=await config();}catch{return;}if(!ready.giftRequestsEnabled)return;
 const form=document.createElement('form');form.id='gift-order-form';form.className='commerce-form';
 form.innerHTML='<div class="section-index">GIFT ORDER</div><h2>기프트 주문 요청</h2><p>수량과 제작 조건을 접수하면 재고·납기와 최종 금액을 확인해드립니다. 접수만으로 결제되거나 제작이 시작되지 않습니다.</p><div class="commerce-fields"><label>주문 수량<input name="quantity" type="number" min="1" max="100000" step="1" inputmode="numeric" required></label><label>희망 수령일 (선택)<input name="requested_date" type="date" min="'+new Date(Date.now()+9*3600000).toISOString().slice(0,10)+'"></label><label>색상·사양 (선택)<input name="variant" maxlength="300" placeholder="예: 흰색, 500mL"></label><label>인쇄 요청 (선택)<textarea name="printing" maxlength="500" rows="3" placeholder="예: 한 면에 로고 1도 인쇄 / 인쇄 없음"></textarea></label><label>포장 요청 (선택)<textarea name="packaging" maxlength="300" rows="2" placeholder="예: 개별 OPP 포장"></textarea></label><label>추가 요청 (선택)<textarea name="notes" maxlength="1000" rows="3"></textarea></label></div><h3>주문자 · 받으실 곳</h3><div class="commerce-fields">'+[
  ['name','받는 분','text','name',60],['phone','연락처','tel','tel',20],['postcode','우편번호','text','postal-code',5],['address','주소','text','address-line1',160],['address_detail','상세 주소','text','address-line2',100]
 ].map(([key,label,type,autocomplete,max])=>`<label>${label}<input name="${key}" type="${type}" autocomplete="${autocomplete}" maxlength="${max}" required ${key==='postcode'?'inputmode="numeric" pattern="[0-9]{5}"':''}></label>`).join('')+'</div>'+evidenceForm(ready.taxInvoiceEnabled)+'<label class="commerce-check"><input type="checkbox" name="consent" required><span>주문 상담·배송과 증빙 발급에 필요한 이름·연락처·주소 및 요청 내용의 수집·이용에 동의합니다. <a href="/privacy.html" target="_blank" rel="noopener">처리 항목과 보유기간 확인 ↗</a></span></label><p class="commerce-feedback" role="status" hidden></p><button type="submit" class="button-primary">기프트 주문 요청 접수하기 →</button>'+notice;
 target.append(form);
 const actions=main.querySelector('.gift-detail-actions');if(actions){const link=document.createElement('a');link.className='button-primary';link.href='#gift-order-form';link.textContent='기프트 주문 요청';actions.prepend(link);}
 const evidenceSelect=form.querySelector('[name=evidence_kind]');
 evidenceSelect.onchange=()=>{const tax=form.querySelector('[data-tax-fields]'),active=evidenceSelect.value==='tax_invoice';tax.hidden=!active;tax.querySelectorAll('input').forEach(input=>{input.disabled=!active;input.required=active;});};evidenceSelect.onchange();
 let key=crypto.randomUUID(),payload,busy=false;
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;busy=true;const button=form.querySelector('button'),feedback=form.querySelector('.commerce-feedback');button.disabled=true;message(feedback,'기프트 주문 요청을 저장하고 있습니다.');
  try{
   if(!payload){const fields=new FormData(form);payload={customer:Object.fromEntries(['name','phone','postcode','address','address_detail'].map(k=>[k,fields.get(k)])),gift:{product_id:target.dataset.giftOrder,quantity:Number(fields.get('quantity')),...Object.fromEntries(['variant','printing','packaging','requested_date','notes'].map(k=>[k,fields.get(k)]))},evidence:{kind:fields.get('evidence_kind')}};payload.customer.consent=fields.has('consent');if(payload.evidence.kind==='tax_invoice')for(const k of ['corp_num','corp_name','ceo_name','address','biz_type','biz_class','email'])payload.evidence[k]=fields.get('tax_'+k);}
   form.querySelectorAll('input,select,textarea').forEach(input=>input.disabled=true);
   await api('session',{});const {order}=await api('gift-create',payload,{'Idempotency-Key':key});location.assign('/orders.html#'+encodeURIComponent(order.id));
  }catch(error){
   message(feedback,error.message);
   if(error.status&&error.status<500&&error.status!==429){payload=undefined;key=crypto.randomUUID();form.querySelectorAll('input,select,textarea').forEach(input=>input.disabled=false);evidenceSelect.onchange();}
   else message(feedback,error.message+' 같은 내용으로 다시 접수 버튼을 눌러주세요.');
   button.disabled=false;busy=false;
  }
 });
}
function documentCard(doc){
 if(!doc)return '';
 const kind={card_receipt:'카드 매출전표',cash_receipt:doc.purpose==='business'?'현금영수증 · 지출증빙':doc.purpose==='income'?'현금영수증 · 소득공제':'현금영수증',tax_invoice:'전자세금계산서'}[doc.kind]||'결제 증빙';
 const status={queued:'발급 대기',processing:'발급 확인 중',retry:'발급 결과 확인 중',review:'발급 확인 필요',issued:'발급 완료',voided:'취소'}[doc.status]||'확인 중';
 const receipt=safeReceiptUrl(doc.receipt_url)?`<p><a href="${esc(doc.receipt_url)}" target="_blank" rel="noopener noreferrer">영수증 조회 · 인쇄 ↗</a></p>`:'';
 return `<div class="commerce-document"><strong>${esc(kind)} · ${esc(status)}</strong>${doc.approval_number?`<p>승인번호 ${esc(doc.approval_number)}</p>`:''}${doc.kind==='tax_invoice'&&doc.status==='issued'?'<p>입력하신 이메일로 발급 안내가 전송됩니다. '+(doc.nts_status==='accepted'?'국세청 전송이 완료되었습니다.':'국세청 전송 결과는 확인 중입니다.')+'</p>':''}${receipt}${doc.status==='review'?'<p>결제 상태와 증빙을 별도로 확인하고 있습니다. 고객센터에 주문번호를 알려주세요.</p>':''}</div>`;
}
function calendarInfo(order,admin){
 if(!admin||!order.rental)return '';
 const c=order.calendar,labels={pending:'캘린더 등록 대기',synced:'장비렌탈 캘린더 등록 확인',canceled:'취소 일정 반영',review:'캘린더 확인 필요',error:'캘린더 재연결 필요',ignored:'캘린더 자동등록 제외'};
 const label=c?labels[c.status]||'캘린더 확인 필요':'결제 확정 후 장비렌탈 캘린더에 자동 등록';
 const reasons={payment_review:'결제 취소 범위를 확인해주세요.',calendar_manually_changed:'캘린더에서 직접 수정한 일정을 확인해주세요.',event_identity_mismatch:'연결된 일정의 주문번호를 확인해주세요.',calendar_or_storage_unavailable:'자동 재시도 중입니다. 연결 상태를 확인해주세요.'};
 const url=c?.event_url;
 return '<p class="commerce-calendar">'+esc(label)+(c?.error_code?' · '+esc(reasons[c.error_code]||'연결 상태를 확인해주세요.'):'')+(typeof url==='string'&&url.startsWith('https://www.google.com/calendar/event?')||typeof url==='string'&&url.startsWith('https://calendar.google.com/')?' · <a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">일정 열기 ↗</a>':'')+'</p>';
}
function orderCard(order,admin=false){
 const customer=order.customer;
 return `<article class="commerce-order" id="${esc(order.id)}"><header><div><span class="section-index">${esc(order.id)}</span><h2>${order.payment_mode==='test'?'테스트 · ':''}${esc(order.kind==='rental'&&order.state==='REQUESTED'?'대여 일정·요금 확인 중':order.state==='APPROVED'&&!checkoutPaymentOpen?'금액 확인 완료':states[order.state]||'상태 확인 필요')}</h2></div><time>${esc(new Date(order.created_at).toLocaleString('ko-KR'))}</time></header><ul class="commerce-lines">${order.lines.map(p=>`<li><a href="${order.gift?'/gift-item.html?id='+encodeURIComponent(order.gift.product_id):'/item.html?id='+encodeURIComponent(p.id)}">${esc(p.name)}<small>${esc(p.option||'기본 구성')} · ${p.quantity}개</small></a><strong>${money(p.unit_price===null?null:p.unit_price*p.quantity)}</strong></li>`).join('')}</ul><div class="commerce-totals"><span>${order.kind==='rental'?'전체 기간 대여료 '+money(order.subtotal)+' · 방문 수령':'상품 '+money(order.subtotal)+' + 배송 '+(order.gift&&order.total===null?'확인 중':money(order.shipping))}</span><strong>${money(order.total)}</strong></div>${order.kind!=='rental'&&order.fulfillment==='shipped'?`<p class="commerce-shipped">출고 완료 · ${esc(order.carrier)} ${esc(order.tracking)}</p>`:''}${admin&&order.rental&&customer?`<details class="commerce-address"><summary>예약자 정보 확인</summary><p>${esc(customer.name)} · ${esc(customer.phone)}</p></details>`:''}${order.rental?`<dl class="rental-order-schedule"><div><dt>대여 시작일 · 수령 방문</dt><dd>${esc(order.rental.start_date)} ${esc(order.rental.pickup_time)}</dd></div><div><dt>대여 종료일 · 반납 방문</dt><dd>${esc(order.rental.end_date)} ${esc(order.rental.return_time)}</dd></div><div><dt>수령·반납 상태</dt><dd>${order.fulfillment==='shipped'?'반납 완료':order.fulfillment==='processing'?'대여 중':'방문 수령 예정'}</dd></div>${order.rental.actual_pickup_at?`<div><dt>실제 수령 처리</dt><dd>${esc(new Date(order.rental.actual_pickup_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))}</dd></div>`:''}${order.rental.actual_return_at?`<div><dt>실제 반납 처리</dt><dd>${esc(new Date(order.rental.actual_return_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))}</dd></div>`:''}</dl>`:''}${giftInfo(order)}${calendarInfo(order,admin)}${admin&&customer&&!order.rental?`<details class="commerce-address"><summary>배송 정보 확인</summary><p>${esc(customer.name)} · ${esc(customer.phone)}<br>(${esc(customer.postcode)}) ${esc(customer.address)} ${esc(customer.address_detail)}</p></details>`:''}${admin&&customer?.evidence?.kind==='tax_invoice'?`<details class="commerce-address"><summary>세금계산서 요청 정보</summary><p>${esc(customer.evidence.corp_name)} · ${esc(customer.evidence.corp_num)}<br>대표 ${esc(customer.evidence.ceo_name)}<br>${esc(customer.evidence.address)}<br>${esc(customer.evidence.biz_type)} / ${esc(customer.evidence.biz_class)}<br>수신 ${esc(customer.evidence.email)}</p></details>`:''}${!admin?customerShipments(order):''}${documentCard(order.document)}<div class="commerce-actions">${admin?adminActions(order):customerActions(order)}</div><p class="commerce-feedback" role="status" hidden></p></article>`;
}
function customerActions(order){
 if(order.state==='PAID'&&order.document)return '<button type="button" class="button-outline" data-customer-document="refresh">증빙 상태 새로고침</button>'+(order.document.kind==='tax_invoice'&&order.document.status==='issued'?'<button type="button" class="button-outline" data-customer-document="print">세금계산서 조회 · 인쇄 ↗</button>':'');
 if(['APPROVED','PAYMENT_PENDING'].includes(order.state)&&!checkoutPaymentOpen)return '<p>금액이 확인되었습니다. 온라인 결제 연결을 준비 중입니다.</p>';
 if(['APPROVED','PAYMENT_PENDING'].includes(order.state))return `<p>결제 가능 시간: ${esc(new Date(order.quote_expires).toLocaleString('ko-KR'))}까지</p><label class="commerce-check"><input type="checkbox" data-quote-consent><span>${order.kind==='rental'?'대여 구성·방문 일정과 전체 기간 요금':'상품 구성과 배송비를 포함한 확정 금액'} ${money(order.total)}을 확인했습니다.</span></label><button type="button" class="button-primary" data-pay="${esc(order.id)}">${money(order.total)} 결제하기 →</button>`;
 if(order.state==='REQUESTED')return order.kind==='rental'?'<p>재고와 방문 일정 확인 후 전체 기간 요금을 안내해드립니다. 아직 예약이 확정되지 않았습니다.</p>':'<p>재고·납기 확인 후 결제가 열립니다.</p>';
 if(['CONFIRMING','PAYMENT_REVIEW'].includes(order.state))return '<p>결제 결과를 확인하고 있습니다. 중복 결제하지 말고 고객센터에 주문번호를 알려주세요.</p>';
 return '';
}
function lineKey(line){return JSON.stringify([line.id,line.option||'']);}
function originalShipments(order){
 if(order.shipments?.length)return order.shipments;
 if(order.kind!=='rental'&&order.fulfillment==='shipped')return [{id:'legacy',purpose:'original',items:order.lines,carrier:order.carrier,tracking:order.tracking,created_at:null}];
 return [];
}
function remainingShipmentItems(order){
 const shipped=new Map();
 for(const shipment of originalShipments(order).filter(s=>s.purpose!=='exchange'))for(const line of shipment.items)shipped.set(lineKey(line),(shipped.get(lineKey(line))||0)+line.quantity);
 return order.lines.map(line=>({...line,quantity:Math.max(0,line.quantity-(shipped.get(lineKey(line))||0))})).filter(line=>line.quantity>0);
}
function quantityFields(items,defaultAll=true){return items.map((line,i)=>`<label class="commerce-quantity"><span>${esc(line.name||line.id)}<small>${esc(line.option||'기본 구성')} · 최대 ${line.quantity}개</small></span><input type="number" data-item-index="${i}" value="${defaultAll?line.quantity:0}" min="0" max="${line.quantity}" step="1" inputmode="numeric" aria-label="${esc(line.name||line.id)} 처리 수량" required></label>`).join('');}
function shipmentTransport(shipment={}){return `<div class="commerce-transport"><label>택배사<input name="carrier" value="${esc(shipment.carrier||'')}" maxlength="40" required></label><label>운송장 번호<input name="tracking" value="${esc(shipment.tracking||'')}" maxlength="30" pattern="[0-9][0-9-]{5,29}" required></label></div>`;}
const caseStates={requested:'접수',approved:'승인',returning:'회수 중',received:'회수 확인',closed:'기록 종결',rejected:'접수 거절'};
function caseRemaining(order,shipment){
 const used=new Map();for(const claim of order.admin_cases||[])if(claim.shipment_id===shipment.id&&claim.status!=='rejected')for(const line of claim.items)used.set(lineKey(line),(used.get(lineKey(line))||0)+line.quantity);
 return shipment.items.map(line=>({...line,quantity:Math.max(0,line.quantity-(used.get(lineKey(line))||0))})).filter(line=>line.quantity>0);
}
function adminShipping(order){
 const shipments=originalShipments(order),eligible=order.state==='PAID'&&order.payment_mode==='live',canManage=order.payment_mode==='live'&&['PAID','PAYMENT_REVIEW','CANCELED'].includes(order.state),remaining=remainingShipmentItems(order);
 if(!eligible&&!shipments.length&&!(order.admin_cases||[]).length)return '';
 let html='<section class="commerce-fulfillment"><h3>출고 · 반품 · 교환</h3>'+adminWorkflowForm(order);
 if(eligible&&!order.admin_shipping_label&&remaining.length)html+=`<form class="commerce-shipping" data-shipment-create><h4>${shipments.length?'남은 상품 출고':'상품 출고'}</h4><p>이번에 보낼 수량을 입력하세요. 0개인 품목은 다음 출고에 남습니다.</p><div class="commerce-quantities">${quantityFields(remaining)}</div>${shipmentTransport()}<button class="button-primary">선택 수량 출고 처리</button></form>`;
 for(const shipment of shipments){
  const available=caseRemaining(order,shipment);
  html+=`<details class="commerce-shipment"><summary>${shipment.purpose==='exchange'?'교환 재출고':'상품 출고'} · ${esc(shipment.carrier)} ${esc(shipment.tracking)}</summary><ul>${shipment.items.map(line=>'<li>'+esc(line.name||line.id)+' · '+esc(line.option||'기본 구성')+' · '+line.quantity+'개</li>').join('')}</ul>${shipment.created_at?'<p>'+new Date(shipment.created_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})+'</p>':'<p>기존 주문의 출고 내역</p>'}${canManage&&!shipment.id.startsWith('SH-GF-')?`<form data-shipment-update="${esc(shipment.id)}">${shipmentTransport(shipment)}<button class="button-outline">운송정보 수정</button></form>`:''}${canManage&&available.length?`<details class="commerce-case-open"><summary>이 출고의 반품·교환 접수</summary><form data-case-create="${esc(shipment.id)}"><label>접수 유형<select name="kind"><option value="return">반품</option><option value="exchange">교환</option></select></label><div class="commerce-quantities">${quantityFields(available,false)}</div><label>접수 사유<textarea name="reason" minlength="2" maxlength="500" rows="3" required></textarea></label><p>이 기록은 결제 취소·환불을 실행하지 않습니다. 환불 결과는 결제사에서 별도로 확인하세요.</p><button class="button-outline">선택 수량 접수</button></form></details>`:''}</details>`;
 }
 for(const claim of order.admin_cases||[]){
  const next={requested:['approved','rejected'],approved:['returning','received','rejected'],returning:['received','rejected'],received:['closed']}[claim.status]||[];
  const choices=[claim.status,...next.filter(status=>status!=='closed'||claim.kind!=='exchange'||claim.replacement_complete)];
  html+=`<div class="commerce-case"><h4>${claim.kind==='exchange'?'교환':'반품'} · ${esc(caseStates[claim.status]||claim.status)}</h4><p>${claim.items.map(line=>esc(line.name||line.id)+' '+line.quantity+'개').join(' / ')}</p><p>사유: ${esc(claim.reason)}</p>${claim.note?'<p>처리 메모: '+esc(claim.note)+'</p>':''}${claim.return_carrier?'<p>회수 운송정보: '+esc(claim.return_carrier)+' '+esc(claim.return_tracking)+'</p>':''}${choices.length?`<form data-case-update="${esc(claim.id)}"><label>다음 상태<select name="status">${choices.map(status=>'<option value="'+status+'">'+(status===claim.status?'상태 유지 · 메모/운송정보 수정':caseStates[status])+'</option>').join('')}</select></label><label>처리 메모 (종결·거절 시 사유 필수)<textarea name="note" maxlength="1000" rows="2">${esc(claim.note||'')}</textarea></label><div class="commerce-transport"><label>회수 택배사 (선택)<input name="carrier" maxlength="40" value="${esc(claim.return_carrier||'')}"></label><label>회수 운송장 (선택)<input name="tracking" maxlength="30" pattern="[0-9][0-9-]{5,29}" value="${esc(claim.return_tracking||'')}"></label></div><button class="button-outline">처리 기록 저장</button></form>`:''}${eligible&&claim.kind==='exchange'&&claim.status==='received'&&claim.replacement_remaining?.length?`<form data-exchange-ship="${esc(claim.id)}"><h4>교환품 재출고</h4><div class="commerce-quantities">${quantityFields(claim.replacement_remaining)}</div>${shipmentTransport()}<button class="button-primary">교환품 출고 처리</button></form>`:''}<p class="commerce-note">반품·교환 기록과 실제 환불 상태는 별도로 확인합니다.</p></div>`;
 }
 return html+'</section>';
}
function customerShipments(order){
 const list=originalShipments(order);if(!list.length||order.kind==='rental')return '';
 return '<section class="commerce-deliveries"><h3>출고 내역</h3>'+list.map(shipment=>'<div><strong>'+(shipment.purpose==='exchange'?'교환품':'상품')+' · '+esc(shipment.carrier)+' '+esc(shipment.tracking)+'</strong><p>'+shipment.items.map(line=>esc(line.name||line.id)+' '+line.quantity+'개').join(' / ')+'</p></div>').join('')+'</section>';
}
function adminActions(order){
 const rental=order.kind==='rental';
 const prices=rental?order.lines.map((line,i)=>`<label>${esc(line.name)} · 전체 기간 1개당 확정 요금<input type="number" data-rental-price="${i}" value="${line.unit_price??''}" min="1" max="100000000" step="1" inputmode="numeric" required></label>`).join(''):'';
 const giftPrices=order.gift?order.lines.map((line,i)=>`<label>${esc(line.name)} · 인쇄·포장·부가세 포함 1개당 판매가<input type="number" data-gift-price="${i}" value="${line.unit_price??''}" min="1" max="100000000" step="1" required></label>`).join('')+`<label>부가세 포함 배송비<input type="number" data-gift-shipping value="${order.total===null?'':order.shipping}" min="0" max="10000000" step="1" required></label><label class="commerce-check"><input type="checkbox" data-gift-confirmed><span>공급처의 현재 판매 가능 여부와 요청한 인쇄·포장·납기를 확인했으며, 위 단가에 인쇄·포장·부가세가 모두 포함되어 있습니다.</span></label>`:'';
 const approve=['REQUESTED','APPROVED'].includes(order.state)?prices+giftPrices+`<label class="commerce-check"><input type="checkbox" data-stock><span>${rental?'이 요청의 수량·구성별 재고와 수령·반납 방문 일정을 확인했습니다.':'이 주문의 수량·옵션별 재고와 납기를 확인했습니다.'}</span></label><button type="button" class="button-primary" data-approve>${rental?'전체 기간 대여 요금 확정':'주문 금액 확정'}</button>`:'';
 const visits=rental&&order.state==='PAID'&&order.payment_mode==='live'?(order.fulfillment==='unfulfilled'?'<button type="button" class="button-primary" data-rental-pickup>방문 수령 완료 처리</button>':order.fulfillment==='processing'?'<button type="button" class="button-primary" data-rental-return>방문 반납 완료 처리</button>':'<p>반납 완료</p>'):'';
 const ship=!rental?adminShipping(order):'';
 const reconcile=['CONFIRMING','PAYMENT_REVIEW','PAID','CANCELED'].includes(order.state)?'<button type="button" class="button-outline" data-reconcile>결제사 상태 다시 확인</button>':'';
 const receipt=order.document&&['retry','review','queued'].includes(order.document.status)?'<button type="button" class="button-outline" data-document-retry>증빙 상태 확인 · 재처리</button>':'';
 const cancel=['REQUESTED','APPROVED'].includes(order.state)?`<details class="commerce-cancel"><summary>미결제 접수 취소</summary><form data-cancel-request><p>결제를 시작하지 않은 주문의 접수를 취소합니다. 결제된 주문의 환불은 결제사에서 확인해야 합니다.</p><label>취소 사유<textarea name="reason" minlength="2" maxlength="500" rows="3" required></textarea></label><label class="commerce-check"><input type="checkbox" required><span>주문번호와 취소 사유를 확인했습니다.</span></label><button class="button-outline">접수 취소 확정</button></form></details>`:'';
 const locked=['PAYMENT_PENDING','CONFIRMING'].includes(order.state);
 const memo=`<form class="commerce-memo" data-admin-note><label>담당자 메모<textarea name="note" maxlength="2000" rows="3" placeholder="재고 확인 내용, 고객 요청과 다음 처리 내용을 기록하세요." ${locked?'disabled':''}>${esc(order.admin_note?.text||'')}</textarea></label><div><span>${locked?'결제 진행 중에는 메모를 변경할 수 없습니다.':order.admin_note?.updated_at?'마지막 저장 '+new Date(order.admin_note.updated_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'관리자에게만 보입니다.'}</span><button class="button-outline" ${locked?'disabled':''}>메모 저장</button></div></form>`;
 const canceled=order.admin_cancellation?`<p class="commerce-cancel-reason">접수 취소 사유: ${esc(order.admin_cancellation.reason)}</p>`:'';
 const qa=commerceTesting&&order.payment_mode==='test'&&order.state==='PAID'?'<button type="button" class="button-outline" data-qa-cancel>테스트 결제 취소</button>'+(!rental&&order.fulfillment!=='shipped'?'<button type="button" class="button-outline" data-qa-deliver>테스트 배송 완료 · 모의 처리</button>':''):'';
 return approve+visits+ship+reconcile+receipt+cancel+canceled+memo+qa;
}
let sdk;
function loadToss(){return sdk||(sdk=new Promise((resolve,reject)=>{
 const script=document.createElement('script');script.src='https://js.tosspayments.com/v2/standard';
 script.onload=()=>{if(typeof window.TossPayments==='function')resolve(window.TossPayments);else{sdk=null;script.remove();reject(Error('토스페이먼츠 결제창을 불러오지 못했습니다.'));}};
 script.onerror=()=>{sdk=null;script.remove();reject(Error('결제창을 불러오지 못했습니다. 다시 시도해주세요.'));};document.head.append(script);
}).catch(error=>{sdk=null;throw error;}));}
function deviceType(){return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)||(/Macintosh/i.test(navigator.userAgent)&&navigator.maxTouchPoints>1)?'MOBILE':'WEB';}
function paymentRequest(value,order){
 const r=value.request,success=new URL(r?.successUrl||'',location.origin);
 if(value.provider!=='toss'||!['test','live'].includes(value.mode)||!new RegExp('^'+value.mode+'_ck_[a-zA-Z0-9_-]+$').test(value.clientKey||'')||!Number.isSafeInteger(value.amount)||value.amount<1||value.amount>100000000||value.orderId!==order.id||value.amount!==order.total||r?.amount?.currency!=='KRW'||r.amount.value!==value.amount||r.orderId!==value.orderId||!['CARD','TRANSFER'].includes(r.method)||success.origin!==location.origin||success.pathname!=='/api/toss-return'||!success.searchParams.get('token')||r.failUrl!==location.origin+'/orders.html?result=closed')throw Error('결제 요청 정보를 확인해주세요.');
 return r;
}
function safeReceiptUrl(value){try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&!u.port&&['dashboard.tosspayments.com','pgweb.tosspayments.com','receipt.tosspayments.com'].includes(u.hostname)?u.href:null;}catch{return null;}}
async function paymentTest(){
 const holder=main.querySelector('#payment-demo'),feedback=main.querySelector('#preview-result');
 const closed=new URLSearchParams(location.search).get('result')==='closed';if(location.search)history.replaceState(null,'','/payment-test.html');
 if(closed)message(feedback,'테스트 결제창을 닫았습니다. 다시 테스트할 수 있습니다.');
 try{
  const response=await fetch('/api/toss-review?action=config',{cache:'no-store'}),ready=await response.json();if(!response.ok||ready.mode!=='test'||!Array.isArray(ready.products))throw Error('테스트 연결 상태를 확인하지 못했습니다.');
  holder.innerHTML='<h2>토스페이먼츠 테스트 결제</h2><p>실제 금액은 청구되지 않으며 상품 주문이나 렌탈 예약이 생성되지 않습니다.</p><label>테스트 상품<select data-review-product>'+ready.products.map(p=>'<option value="'+esc(p.id)+'">'+esc((p.kind==='rental'?'렌탈':'구매')+' · '+p.name)+'</option>').join('')+'</select></label><p data-review-amount></p><div class="commerce-actions"><button type="button" class="button-primary" data-review-method="CARD" disabled>카드 테스트 결제창</button><button type="button" class="button-outline" data-review-method="TRANSFER" disabled>계좌이체 테스트 결제창</button></div><p data-review-status role="status">'+(ready.configured?'안전한 테스트 결제창을 불러오고 있습니다.':'테스트 상점 연결 대기 중입니다. 연결이 완료되면 이 화면에서 결제창과 승인·취소 결과를 확인할 수 있습니다.')+'</p><p><a href="/terms.html">이용약관</a> · <a href="/privacy.html">개인정보 처리 안내</a> · <a href="/shipping.html">배송·교환·반품 안내</a></p>';
  const select=holder.querySelector('[data-review-product]'),status=holder.querySelector('[data-review-status]'),buttons=[...holder.querySelectorAll('[data-review-method]')];
  const update=()=>{const p=ready.products.find(p=>p.id===select.value);holder.querySelector('[data-review-amount]').textContent=p?'테스트 금액 '+money(p.amount):'테스트 가능한 상품을 확인하고 있습니다.';};select.onchange=update;update();
  if(!ready.configured||!ready.products.length)return;
  const provider=await loadToss();buttons.forEach(b=>b.disabled=false);status.textContent='결제수단을 선택하면 토스 테스트 결제창이 열립니다.';
  for(const button of buttons)button.onclick=async()=>{
   buttons.forEach(b=>b.disabled=true);status.textContent='토스 테스트 결제창으로 연결하고 있습니다.';
   try{
    const product=ready.products.find(p=>p.id===select.value),response=await fetch('/api/toss-review?action=prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:product.id,method:button.dataset.reviewMethod})}),value=await response.json();
    if(!response.ok)throw Error(value.error||'테스트 요청을 확인해주세요.');
    const r=value.request,success=new URL(r?.successUrl||'',location.origin);
    if(value.mode!=='test'||value.provider!=='toss'||!/^test_ck_[a-zA-Z0-9_-]+$/.test(value.clientKey||'')||value.amount!==product.amount||!Number.isSafeInteger(product.amount)||product.amount<1||r?.amount?.value!==product.amount||r.amount.currency!=='KRW'||r.orderId!==value.orderId||!/^NDTEST_[a-f0-9]{24}$/.test(value.orderId)||r.method!==button.dataset.reviewMethod||success.origin!=='https://shop.nadaun.co'||success.pathname!=='/api/toss-review'||success.searchParams.get('action')!=='return'||!success.searchParams.get('token')||r.failUrl!=='https://shop.nadaun.co/payment-test.html?result=closed')throw Error('안전한 테스트 결제 요청을 확인하지 못했습니다.');
    await provider(value.clientKey).payment({customerKey:provider.ANONYMOUS}).requestPayment(r);
   }catch(error){status.textContent=error?.code==='USER_CANCEL'?'테스트 결제창을 닫았습니다. 다시 테스트할 수 있습니다.':error.message||'테스트 결제창 연결을 확인해주세요.';buttons.forEach(b=>b.disabled=false);}
  };
 }catch(error){holder.innerHTML='<h2>토스페이먼츠 테스트 결제</h2><p>테스트 연결을 확인하고 있습니다. 잠시 후 다시 확인해주세요.</p>';message(feedback,error.message);}
}

async function pay(order,card,button){
 if(button.disabled)return;
 const feedback=card.querySelector('.commerce-feedback');
 if(!card.querySelector('[data-quote-consent]').checked){message(feedback,'확정 금액을 확인하고 동의해주세요.');return;}
 button.disabled=true;message(feedback,'토스페이먼츠 결제창으로 연결하고 있습니다.');
 try{
  const provider=await loadToss(),value=await api('start',{id:order.id,quote_version:order.quote_version,device:deviceType()}),request=paymentRequest(value,order);
  await provider(value.clientKey).payment({customerKey:provider.ANONYMOUS}).requestPayment(request);
 }catch{message(feedback,'결제창이 닫혔거나 연결을 완료하지 못했습니다. 주문 상태를 확인한 뒤 다시 시도해주세요.');button.disabled=false;}
}
async function orders(){
 const container=main.querySelector('#commerce-content'),feedback=main.querySelector('#commerce-status');
 try{
  const ready=await config();checkoutPaymentOpen=ready.ordersEnabled===true;
  const params=new URLSearchParams(location.search);
  if(params.has('result'))history.replaceState(null,'','/orders.html'+location.hash);
  if(params.get('result')==='closed')message(feedback,'결제창을 닫았습니다. 아래 주문 상태를 확인해주세요.');
  else if(params.has('result'))message(feedback,'서버에 저장된 주문·결제 상태를 확인해주세요.');
  const {orders:list}=await api('orders');container.innerHTML=list.length?list.map(p=>orderCard(p)).join(''):'<div class="commerce-empty"><h2>접수한 주문이 없습니다.</h2><a href="/catalog.html">상품 둘러보기 →</a></div>';
  let membership;try{membership=await (await fetch('/api/members?action=me',{cache:'no-store'})).json();}catch{}
  for(const order of list){const card=document.getElementById(order.id),button=card.querySelector('[data-pay]');if(button)button.onclick=()=>pay(order,card,button);
   if(membership?.authenticated&&membership.policy?.earn_enabled&&order.kind==='purchase'&&order.state==='PAID'&&order.fulfillment==='shipped'&&order.shipments?.length&&order.shipments.filter(s=>s.purpose==='original').every(s=>s.delivery_status==='delivered')){const confirm=document.createElement('button');confirm.type='button';confirm.className='button-outline';confirm.textContent='구매확정 · 적립금 받기';card.querySelector('.commerce-actions').append(confirm);confirm.onclick=async()=>{confirm.disabled=true;try{const r=await fetch('/api/members?action=confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:order.id})}),v=await r.json();if(!r.ok)throw Error(v.error);confirm.textContent='구매확정 완료';message(card.querySelector('.commerce-feedback'),'구매확정과 적립을 확인했습니다. 마이페이지에서 잔액을 확인해주세요.');}catch(e){message(card.querySelector('.commerce-feedback'),e.message);confirm.disabled=false;}};}
   for(const control of card.querySelectorAll('[data-customer-document]'))control.onclick=async()=>{
    control.disabled=true;const feedback=card.querySelector('.commerce-feedback');message(feedback,'증빙 상태를 확인하고 있습니다.');
    try{const result=await api(control.dataset.customerDocument==='print'?'document-print':'document-refresh',{id:order.id});
     if(control.dataset.customerDocument==='print'){const url=new URL(result.url);if(url.protocol!=='https:'||url.username||url.password||url.port||!['www.popbill.com','test.popbill.com'].includes(url.hostname))throw Error('안전한 세금계산서 주소를 확인하지 못했습니다.');location.assign(url.href);}
     else {await orders();message(main.querySelector('#commerce-status'),'최신 증빙 상태를 확인했습니다.');}
    }catch(error){message(feedback,error.message);control.disabled=false;}
   }
  }
  if(location.hash){const id=decodeURIComponent(location.hash.slice(1));document.getElementById(id)?.scrollIntoView({block:'start'});}
 }catch(error){message(feedback,error.message);container.innerHTML=error.status===401?'<p><a class="button-primary" href="/account.html">로그인 · 회원가입 →</a></p><p>비회원 주문은 접수한 브라우저에서 확인해주세요.</p>':'';}
}
function adminReadiness(ready){
 const provider={toss:'토스페이먼츠'}[ready.paymentProvider]||'확인 필요';
 const rows=[['현재 결제대행사',provider],['고객 주문·결제',ready.ordersEnabled===true?'접수 가능':'오픈 준비 중'],['렌탈 온라인 접수',ready.rentalRequestsEnabled===true?'접수 가능':'오픈 준비 중'],['기프트 주문 요청',ready.giftRequestsEnabled===true?'접수 가능':'오픈 준비 중'],['전자세금계산서',ready.taxInvoiceEnabled===true?'발급 연결됨':'발급 연결 준비 중']];
 return '<div class="commerce-admin-summary" aria-label="운영 연결 상태">'+rows.map(([label,value])=>'<div><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></div>').join('')+'</div><p class="commerce-note">현금영수증 소득공제·사업자 지출증빙은 결제대행사에서 처리합니다. 전자세금계산서는 별도 발급 연결이 필요합니다.</p>';
}
const adminColumns=[['order','주문'],['customer','고객'],['product','상품·일정'],['amount','주문 금액'],['payment','결제 상태'],['shipping','배송·송장'],['next','다음 처리']];
const adminPreferenceKey='nadaun-admin-view-v1';
const adminWorkflowStates={preparing:'상품 준비',ready:'배송 대기',in_transit:'배송 중',delivered:'배송 완료'};
function adminFilterMetadata(input={}){
 if(!input||typeof input!=='object')input={};
 const result={};
 for(const key of ['from','to'])if(typeof input[key]==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(input[key])&&!Number.isNaN(Date.parse(input[key]))&&new Date(input[key]).toISOString().slice(0,10)===input[key])result[key]=input[key];
 const fields={basis:['created','paid'],mode:['operational','live','test','all'],kind:['','purchase','rental'],state:['',...Object.keys(states)],fulfillment:['','unfulfilled','processing','shipped'],document:['','queued','processing','issued','retry','review','voided','missing'],queue:['','purchase-shipping','purchase-preparing','purchase-ready','purchase-transit','purchase-delivered','purchase-cases','rental-pickup','rental-return','payment-review'],searchField:['all','order','customer','tracking']};
 for(const [key,values]of Object.entries(fields))if(values.includes(input[key]))result[key]=input[key];
 return result;
}
function adminPreferences(value){
 const v=value&&typeof value==='object'?value:{};
 const columns=Array.isArray(v.columns)?adminColumns.map(c=>c[0]).filter(id=>id==='order'||v.columns.includes(id)):adminColumns.map(c=>c[0]);
 const presets=Array.isArray(v.presets)?v.presets.slice(0,8).map(p=>adminFilterMetadata(p)).filter(p=>p.from&&p.to):[];
 return {columns,density:v.density==='compact'?'compact':'comfortable',layout:v.layout==='cards'?'cards':'table',filtersOpen:v.filtersOpen!==false,presets};
}
function adminReadPreferences(){try{return adminPreferences(JSON.parse(localStorage.getItem(adminPreferenceKey)||'null'));}catch{return adminPreferences();}}
function adminSavePreferences(value){const prefs=adminPreferences(value);try{localStorage.setItem(adminPreferenceKey,JSON.stringify(prefs));}catch{}return prefs;}
function adminPresetTitle(p){
 const queue={ 'purchase-shipping':'구매 출고','purchase-preparing':'상품 준비','purchase-ready':'배송 대기','purchase-transit':'배송 중','purchase-delivered':'배송 완료','purchase-cases':'반품·교환','rental-pickup':'렌탈 수령','rental-return':'렌탈 반납','payment-review':'결제 확인'};
 return [p.kind==='rental'?'렌탈':p.kind==='purchase'?'구매':'전체',queue[p.queue]||states[p.state]||'전체 상태',p.from+' — '+p.to].join(' · ');
}
function adminViewControls(prefs){
 return `<details class="commerce-view-settings"><summary>목록 설정</summary><div class="commerce-view-panel"><fieldset><legend>보기 방식</legend>${[['table','표'],['cards','카드']].map(([v,label])=>`<label><input type="radio" name="admin-layout" value="${v}" ${prefs.layout===v?'checked':''}>${label}</label>`).join('')}</fieldset><fieldset><legend>목록 간격</legend>${[['comfortable','넓게'],['compact','촘촘하게']].map(([v,label])=>`<label><input type="radio" name="admin-density" value="${v}" ${prefs.density===v?'checked':''}>${label}</label>`).join('')}</fieldset><fieldset class="commerce-column-options"><legend>표시할 항목</legend>${adminColumns.map(([id,label])=>`<label><input type="checkbox" data-admin-column="${id}" ${prefs.columns.includes(id)?'checked':''} ${id==='order'?'disabled':''}>${label}</label>`).join('')}</fieldset><button type="button" class="button-outline" data-view-reset>기본 보기로</button></div></details>`;
}
function adminPresetControls(prefs){return `<div class="commerce-saved-filters"><label>저장한 조건<select data-filter-preset><option value="">조건 선택</option>${prefs.presets.map((p,i)=>'<option value="'+i+'">'+esc(adminPresetTitle(p))+'</option>').join('')}</select></label><button type="button" class="button-outline" data-preset-apply>적용</button><button type="button" class="button-outline" data-preset-delete>삭제</button><button type="button" class="button-outline" data-preset-save>현재 조회 조건 저장</button><span>검색어·고객정보는 저장하지 않습니다.</span></div>`;}
function adminShipmentSummary(order){
 if(order.kind==='rental')return order.fulfillment==='shipped'?'반납 완료':order.fulfillment==='processing'?'대여 중':'수령 예정';
 const stage=order.purchase_workflow?.stage;
 const label=adminWorkflowStates[stage]|| (order.fulfillment==='shipped'?'출고 완료':order.fulfillment==='processing'?'일부 출고':'출고 전');
 const auto=order.admin_shipping_label,autoText=auto&&!['in_transit','delivered'].includes(auto.status)?'<small>자동 송장 · '+esc(({pending:'접수 결과 확인 중',registered:'인쇄 대기',printed:'발급 완료 · 집하 전',in_transit:'배송 중',delivered:'배송 완료',review:'확인 필요'})[auto.status]||'확인 필요')+'</small>'+ (auto.tracking?'<small>'+esc(auto.carrier)+' '+esc(auto.tracking)+'</small>':''):'';
 const shipments=originalShipments(order);return autoText+'<strong>'+esc(label)+'</strong>'+shipments.map(s=>'<small>'+esc(s.carrier)+' '+esc(s.tracking)+'</small>').join('')+(stage==='delivered'?'<small>'+(order.purchase_workflow?.delivery_source==='goodsflow'?'택배사 배송 완료 확인':'관리자 수령 확인')+'</small>':'');
}
function adminWorkflowForm(order){
 if(order.kind==='rental'||order.state!=='PAID'||order.payment_mode!=='live')return '';
 const stage=order.purchase_workflow?.stage||'preparing',shipped=originalShipments(order).some(s=>s.purpose!=='exchange');
 if(stage==='delivered')return '<p class="commerce-note">배송 완료 · '+(order.purchase_workflow?.delivery_source==='goodsflow'?'택배사에서 확인한 배송 완료입니다.':'관리자가 고객 수령을 확인한 기록입니다.')+'</p>';
 if(order.admin_shipping_label&&!shipped)return '<p class="commerce-note">자동 송장 접수 건입니다. 송장 조회·인쇄 기능을 이용해주세요.</p>';
 if(shipped&&remainingShipmentItems(order).length)return '<p class="commerce-note">일부 상품 배송 중입니다. 남은 상품 출고 후 전체 수령을 확인할 수 있습니다.</p>';
 const choices=shipped?[['delivered','배송 완료 · 고객 수령 확인']]:[['preparing','상품 준비'],['ready','배송 대기']];
 return `<form class="commerce-workflow-form" data-workflow><label>배송 처리 단계<select name="stage">${choices.map(([v,label])=>'<option value="'+v+'" '+(stage===v?'selected':'')+'>'+label+'</option>').join('')}</select></label>${shipped?'<label class="commerce-check"><input type="checkbox" required><span>전체 출고 상품의 고객 수령을 확인했습니다.</span></label>':''}<button class="button-outline">배송 단계 저장</button><p class="commerce-note">배송 중은 실제 출고 내역으로 표시합니다. 배송 완료는 관리자의 수령 확인 기록입니다.</p></form>`;
}
function adminPrintDocument(orders,kind='order'){
 const statement=kind==='statement',title=statement?'거래명세서':'주문서';
 return '<section class="commerce-print-area" aria-label="선택 주문서 인쇄">'+orders.map(o=>`<article class="commerce-print-order"><header><strong>나다운 스페이스 · ${title}</strong><h1>${esc(o.id)}</h1><p>${esc(new Date(o.created_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))} · ${o.kind==='rental'?'렌탈':'구매'} · ${esc(states[o.state]||'상태 확인')}</p></header><p>${esc(o.customer?.name)} · ${esc(o.customer?.phone)}<br>${o.kind==='rental'?'':esc([o.customer?.postcode,o.customer?.address,o.customer?.address_detail].filter(Boolean).join(' '))}</p>${o.rental?'<p>수령 '+esc(o.rental.start_date+' '+o.rental.pickup_time)+' / 반납 '+esc(o.rental.end_date+' '+o.rental.return_time)+'</p>':''}<table><thead><tr><th>상품·옵션</th><th>수량</th>${statement?'<th>단가</th>':''}<th>금액</th></tr></thead><tbody>${o.lines.map(l=>'<tr><td>'+esc(l.name)+'<small>'+esc(l.option||'기본 구성')+'</small></td><td>'+l.quantity+'</td>'+ (statement?'<td>'+money(l.unit_price)+'</td>':'')+'<td>'+money(l.unit_price===null?null:l.unit_price*l.quantity)+'</td></tr>').join('')}</tbody></table><p class="commerce-print-costs">상품 금액 ${money(o.subtotal)} · ${o.kind==='rental'?'방문 수령':'배송비'} ${money(o.shipping)}</p><p class="commerce-print-total">합계 ${money(o.total)}</p><p>주문 버전 ${esc(o.version??'확인 필요')} · 출력 ${esc(new Date().toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))}</p><p>${statement?'주문 기준 금액으로 작성한 거래명세서입니다. 실제 결제·환불 결과는 별도로 확인하세요.':'주문 처리용 문서입니다.'} 결제 영수증·세금계산서가 아닙니다.</p></article>`).join('')+'</section>';
}
function adminClosePrintPreviews(){for(const dialog of document.querySelectorAll('[data-admin-print-preview]'))dialog.remove();}
function adminOpenPrintPreview(html,title,onError=()=>{}){
 adminClosePrintPreviews();const dialog=document.createElement('dialog');dialog.dataset.adminPrintPreview='';dialog.className='commerce-print-preview';
 dialog.innerHTML='<header><h2>'+esc(title)+' 미리보기</h2><div><button type="button" class="button-primary" data-print-confirm disabled>인쇄</button><button type="button" class="button-outline" data-print-close>닫기</button></div></header><p>내용을 확인한 뒤 인쇄 버튼을 누르세요. 시스템 인쇄에서 PDF로 저장할 수도 있습니다.</p><iframe title="'+esc(title)+' 미리보기" sandbox="allow-same-origin allow-modals"></iframe>';
 const frame=dialog.querySelector('iframe'),button=dialog.querySelector('[data-print-confirm]');
 frame.onload=async()=>{try{if(frame.contentDocument.fonts?.ready)await frame.contentDocument.fonts.ready;button.disabled=false;}catch{button.disabled=false;}};
 button.onclick=()=>{try{frame.contentWindow.print();}catch{onError('인쇄 창을 열지 못했습니다. 다시 시도해주세요.');}};
 dialog.querySelector('[data-print-close]').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();
 document.body.append(dialog);frame.srcdoc=html;dialog.showModal();return dialog;
}
function adminInvoiceTemplate(orders=[]){
 const cell=value=>{let text=String(value??'');if(/^[\s]*[=+@-]/.test(text))text="'"+text;return '"'+text.replace(/"/g,'""')+'"';};
 return '\ufeffoperation,order_id,version,shipment_id,carrier,tracking,item_id,option,quantity\r\n'+orders.map(o=>['ship',o.id,o.version,'','','','','',''].map(cell).join(',')).join('\r\n')+'\r\n';
}
function adminShippingPanel(status){
 const contracts=status?.contracts||[];
 return `<details class="commerce-invoice-panel" data-auto-shipping><summary>자동 송장 출력 · 굿스플로</summary><div class="commerce-invoice-content"><p>${esc(status?.message||'연결 상태 확인 중')}</p><p>배송 대기 주문을 선택하고 수령인·배송지·박스 규격을 확인한 뒤 접수합니다. 같은 계약의 주문을 한 번에 인쇄할 수 있습니다.</p>${status?.enabled?`<div class="commerce-fields"><label>택배 계약<select data-label-contract><option value="">택배 계약 선택</option>${contracts.map(c=>'<option value="'+esc(c.id)+'">'+esc(c.carrier_name+' · '+c.center_name)+'</option>').join('')}</select></label><label>박스 규격<select data-label-box><option value="">계약을 먼저 선택해주세요</option></select></label></div><div class="commerce-invoice-tools"><button class="button-outline" data-label-preview disabled>선택 주문 접수 전 확인</button><button class="button-outline" data-label-sync disabled>선택 주문 송장 조회</button><button class="button-primary" data-label-print disabled>선택 송장 인쇄</button><label class="commerce-check"><input type="checkbox" data-label-reprint><span>이미 발급된 송장 재인쇄</span></label></div><div data-label-result aria-live="polite"></div>`:'<p>API 연결과 우리몰 계약 확인이 끝나면 이곳에서 접수·인쇄를 사용할 수 있습니다. 현재는 아래 송장 파일 등록을 이용해주세요.</p>'}<p class="commerce-note">송장 발급은 배송 시작과 다릅니다. 발급 번호를 먼저 저장하고 택배사 집하 확인 후 배송 중으로 반영합니다. 인쇄 창에서 프린터와 용지를 확인해주세요.</p></div></details>`;
}

function adminInvoicePanel(){return `<details class="commerce-invoice-panel"><summary>송장 일괄 등록</summary><div class="commerce-invoice-content"><h3>1. 양식 준비</h3><p>구매 주문의 택배사·송장을 입력합니다. 한 주문에 여러 품목이 있으면 같은 주문번호와 버전을 사용하세요.</p><div class="commerce-invoice-tools"><button type="button" class="button-outline" data-invoice-template>빈 CSV 양식</button><button type="button" class="button-outline" data-invoice-selected-template disabled>선택 주문 CSV 양식</button></div><details><summary>작성 방법</summary><p>ship은 신규 출고, update는 기존 송장 수정입니다. update는 shipment_id가 필요합니다. ship에서 item_id·option·quantity를 모두 비우면 미출고 상품 전체가 검증 화면에 표시됩니다. 수량을 지정할 때는 세 항목을 함께 입력하세요. 금액 승인·환불은 처리하지 않습니다.</p></details><h3>2. 파일 검증</h3><form data-invoice-upload><label>CSV 또는 XLSX 파일<input type="file" name="invoice" accept=".csv,.xlsx" required></label><p>최대 1MiB · 500행 · 100주문. CSV는 UTF-8, XLSX는 시트 1개로 작성하세요.</p><button class="button-outline">파일 검증하기</button></form><div data-invoice-result aria-live="polite"></div></div></details>`;}
function adminInvoicePreviewMarkup(preview,outcomes={}){
 const errors=(preview.errors||[]).map(e=>'<li>'+esc((e.rows||[]).join(', '))+'행 · '+esc(e.error)+'</li>').join('');
 return `<h3>3. 검증 결과</h3><p>${Number(preview.totals?.orders)||0}주문 · ${Number(preview.totals?.rows)||0}행 · ${Number(preview.totals?.items)||0}개</p>${errors?'<ul class="commerce-invoice-errors">'+errors+'</ul>':''}<div class="commerce-invoice-table-wrap"><table><thead><tr><th>행</th><th>주문 / 작업</th><th>운송정보</th><th>품목</th><th>결과</th></tr></thead><tbody>${(preview.operations||[]).map(op=>{const result=outcomes[op.index];return '<tr><td>'+esc((op.rows||[]).join(', '))+'</td><td>'+esc(op.id)+'<small>'+(op.operation==='update'?'송장 수정':'신규 출고')+'</small></td><td>'+esc(op.carrier)+'<small>'+esc(op.tracking)+'</small></td><td>'+(op.items||[]).map(l=>esc(l.name||l.id)+' · '+esc(l.option||'기본 구성')+' · '+l.quantity+'개').join('<br>')+'</td><td data-invoice-outcome="'+op.index+'">'+(result?esc(result.ok?(result.duplicate?'기존 처리 확인':'처리 완료'):result.error):op.duplicate?'이미 처리된 작업':'검증 완료 · 실행 전')+'</td></tr>';}).join('')}</tbody></table></div>${preview.valid&&preview.preview_token?'<label class="commerce-check"><input type="checkbox" data-invoice-confirm><span>주문번호·운송장·품목 수량을 확인했습니다.</span></label><button type="button" class="button-primary" data-invoice-apply>검증한 송장 등록</button><p class="commerce-note">한 주문씩 처리합니다. 실패하면 중단하며 결과를 확인한 뒤 미완료 작업을 재시도할 수 있습니다.</p>':'<p>오류를 수정한 파일을 다시 검증해주세요.</p>'}`;
}

const adminTabs=[
 {id:'all',label:'전체 주문',count:'orders',filter:{}},
 {id:'requested',label:'재고·일정 확인',count:'requested',filter:{state:'REQUESTED'}},
 {id:'approved',label:'결제 대기',count:'approved',filter:{state:'APPROVED'}},
 {id:'preparing',label:'상품 준비',count:'purchasePreparing',filter:{queue:'purchase-preparing'}},
 {id:'ready',label:'배송 대기',count:'purchaseReady',filter:{queue:'purchase-ready'}},
 {id:'transit',label:'배송 중',count:'purchaseTransit',filter:{queue:'purchase-transit'}},
 {id:'delivered',label:'배송 완료',count:'purchaseDelivered',filter:{queue:'purchase-delivered'}},
 {id:'cases',label:'반품·교환',count:'purchaseCases',filter:{queue:'purchase-cases'}},
 {id:'shipping',label:'출고할 주문',count:'toShip',filter:{queue:'purchase-shipping'}},
 {id:'pickup',label:'렌탈 수령',count:'rentalPickup',filter:{queue:'rental-pickup'}},
 {id:'return',label:'렌탈 반납',count:'rentalReturn',filter:{queue:'rental-return'}},
 {id:'review',label:'결제 확인',count:'paymentReview',filter:{queue:'payment-review'}},
 {id:'canceled',label:'취소',count:'canceled',filter:{state:'CANCELED'}}
];
function adminNext(order){
 if(order.admin_cases?.some(claim=>!['closed','rejected'].includes(claim.status)))return '반품·교환 확인';
 if(order.state==='CANCELED')return '취소 내역 확인';
 if(order.state==='REQUESTED')return order.kind==='rental'?'일정·재고·요금 확인':'재고·납기 확인';
 if(order.state==='APPROVED')return '고객 결제 대기';
 if(['PAYMENT_PENDING','CONFIRMING','PAYMENT_REVIEW'].includes(order.state))return '결제 상태 확인';
 if(order.state==='PAID'&&order.payment_mode==='test')return '테스트 결제';
 if(order.state==='PAID'&&order.kind==='rental')return order.fulfillment==='shipped'?'반납 완료':order.fulfillment==='processing'?'방문 반납 확인':'방문 수령 확인';
 if(order.admin_shipping_label)return ({pending:'접수 결과 조회',registered:'송장 인쇄',printed:'택배사 집하 대기',in_transit:'배송 상태 자동 조회',delivered:'택배사 배송 완료',review:'택배 접수 확인 필요'})[order.admin_shipping_label.status]||'택배 접수 확인 필요';
 if(order.purchase_workflow?.stage==='delivered')return '고객 수령 확인 완료';
 if(order.purchase_workflow?.stage==='preparing')return '상품 준비 · 재고 확인';
 if(order.purchase_workflow?.stage==='in_transit')return remainingShipmentItems(order).length?'남은 상품 출고':'고객 수령 확인';
 if(order.state==='PAID')return order.fulfillment==='shipped'?'출고 완료':'출고·운송장 입력';
 return '주문 상세 확인';
}
function adminTable(orders,expandedId,preferences=adminPreferences(),selection=new Set()){
 if(!orders.length)return '<div class="commerce-empty commerce-admin-empty"><span>조회 결과 0건</span><h2>이 조건에 해당하는 주문이 없습니다.</h2><p>조회 기간이나 주문 상태를 바꿔 확인하세요. 새 주문이 접수되면 이곳에서 처리할 수 있습니다.</p></div>';
 const prefs=adminPreferences(preferences),visible=new Set(prefs.columns);
 const cell=(id,content,cls='')=>`<td data-column="${id}" data-label="${esc(adminColumns.find(c=>c[0]===id)?.[1])}" class="${cls}" ${visible.has(id)?'':'hidden'}>${content}</td>`;
 return `<div class="commerce-table-wrap" data-admin-layout="${prefs.layout}" data-admin-density="${prefs.density}"><table class="commerce-table"><caption class="sr">주문 목록과 다음 처리</caption><thead><tr><th scope="col" class="commerce-select-cell"><input type="checkbox" data-select-page aria-label="현재 페이지 주문 전체 선택"></th>${adminColumns.map(([id,label])=>`<th scope="col" data-column="${id}" ${visible.has(id)?'':'hidden'}>${label}</th>`).join('')}<th scope="col">상세</th></tr></thead><tbody>`+orders.map(order=>{
  const rental=order.kind==='rental',open=expandedId===order.id;
  return `<tr class="commerce-order-row ${open?'is-expanded':''} ${selection.has(order.id)?'is-selected':''}"><td class="commerce-select-cell"><input type="checkbox" data-select-order="${esc(order.id)}" aria-label="${esc(order.id)} 주문 선택" ${selection.has(order.id)?'checked':''}></td>${cell('order',`<span class="commerce-kind">${rental?'렌탈':order.gift?'기프트':'구매'}${order.payment_mode==='test'?' · 테스트':''}</span><strong>${esc(order.id)}</strong><time>${esc(new Date(order.created_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))}</time>`)}${cell('customer',esc(order.customer?.name||'고객 정보 확인'))}${cell('product',`<strong>${esc(order.lines[0]?.name||'상품 확인')}${order.lines.length>1?' 외 '+(order.lines.length-1)+'종':''}</strong><span>${order.lines.reduce((n,p)=>n+p.quantity,0)}개${rental&&order.rental?' · '+esc(order.rental.start_date)+' → '+esc(order.rental.end_date):''}</span>`,'commerce-table-product')}${cell('amount',money(order.total),'commerce-table-money')}${cell('payment',`<span class="commerce-state" data-state="${esc(order.state)}">${esc(states[order.state]||'확인 필요')}</span>`)}${cell('shipping',adminShipmentSummary(order),'commerce-table-shipping')}${cell('next',esc(adminNext(order)))}<td class="commerce-detail-action"><button type="button" class="button-outline" data-open-order="${esc(order.id)}" aria-expanded="${open}" aria-controls="detail-${esc(order.id)}">${open?'닫기':'처리하기'}</button></td></tr><tr class="commerce-detail-row" ${open?'':'hidden'}><td colspan="${prefs.columns.length+2}"><div id="detail-${esc(order.id)}">${orderCard(order,true).replace('</article>','<details class="commerce-history"><summary>처리 이력 확인</summary><div data-history></div></details></article>')}</div></td></tr>`;
 }).join('')+'</tbody></table></div>';
}
const adminDraftStates={draft:'견적 초안',reviewed:'검토 완료',voided:'취소한 견적'};
const adminDraftNotice='관리자 내부 견적입니다. 저장·검토해도 고객 주문, 재고 예약, 결제 요청 또는 고객 알림이 생성되지 않습니다.';
function adminDraftInput(values,rows,existing){
 if(!rows.length||rows.length>30)throw Error('상품 구성을 1~30개 선택해주세요.');
 const input={kind:values.kind,customer:{},items:rows.map(r=>({id:r.id,option:r.option||'',quantity:Number(r.quantity)})),note:values.note||''};
 for(const key of ['name','phone','email','postcode','address','address_detail'])input.customer[key]=String(values[key]||'').trim();
 if(input.items.some(r=>!Number.isSafeInteger(r.quantity)||r.quantity<1||r.quantity>99))throw Error('상품별 수량은 1~99개로 입력해주세요.');
 if(input.kind==='rental'){
  input.rental={};for(const key of ['start_date','end_date','pickup_time','return_time'])input.rental[key]=String(values[key]||'');
  const any=rows.some(r=>r.unit_price!==null&&r.unit_price!==undefined&&r.unit_price!=='');
  if(any){if(rows.some(r=>!Number.isSafeInteger(Number(r.unit_price))||Number(r.unit_price)<1||Number(r.unit_price)>100000000))throw Error('전체 대여 기간의 단가를 모든 상품에 입력하거나, 모두 비워 미확정 초안으로 저장해주세요.');input.rental_prices=rows.map(r=>({id:r.id,option:r.option||'',unit_price:Number(r.unit_price)}));}
 }
 if(existing?.id){input.id=existing.id;input.version=existing.version;}
 return input;
}
function adminDraftRows(rows,kind,readonly=false){
 if(!rows.length)return '<p class="commerce-empty">상품을 검색하여 견적에 추가하세요.</p>';
 return '<div class="commerce-draft-lines">'+rows.map((r,i)=>`<div class="commerce-draft-line"><div><strong>${esc(r.name)}</strong><small>${esc(r.option||'기본 구성')}</small></div><label>수량<input type="number" data-draft-quantity="${i}" value="${Number(r.quantity)||1}" min="1" max="99" step="1" required ${readonly?'disabled':''}></label>${kind==='rental'?'<label>전체 기간 1개당 단가<input type="number" data-draft-price="'+i+'" value="'+(r.unit_price==null?'':esc(r.unit_price))+'" min="1" max="100000000" step="1" placeholder="미확정" '+(readonly?'disabled':'')+'></label>':'<span class="commerce-draft-price">'+money(r.unit_price)+'<small>1개당 · 저장 시 서버 가격 확인</small></span>'}${readonly?'':'<button type="button" class="button-outline" data-draft-remove="'+i+'">제외</button>'}</div>`).join('')+'</div>';
}
function adminDraftProducts(products){
 if(!products.length)return '<p>선택 가능한 상품이 없습니다. 상품명이나 상품번호를 다시 확인하세요.</p>';
 return products.map((p,i)=>`<div class="commerce-draft-product"><div><strong>${esc(p.name)}</strong><small>${esc(p.id)} · ${p.kind==='rental'?'렌탈 · 기간 단가 직접 확인':money(p.price)}</small></div>${p.disabled?'<span>'+esc(p.notice||'옵션 상담이 필요한 상품')+'</span>':p.options?.length?'<label><span class="sr">'+esc(p.name)+' 옵션</span><select data-draft-option="'+i+'">'+p.options.map(o=>'<option value="'+esc(o.name)+'" '+(o.disabled?'disabled':'')+'>'+esc(o.name||'기본 구성')+(o.disabled?' · 선택 불가':'')+'</option>').join('')+'</select>':'<span>기본 구성</span>'}<button type="button" class="button-outline" data-draft-add="${i}" ${p.disabled||p.options?.length&&!p.options.some(o=>!o.disabled)?'disabled':''}>추가</button></div>`).join('');
}
async function adminGet(action,params={}){
 const response=await fetch('/api/orders?'+new URLSearchParams({action,...params}),{credentials:'same-origin',cache:'no-store'}),value=await response.json();
 if(!response.ok){const error=Error(value.error||'관리자 자료를 확인하지 못했습니다.');error.status=response.status;throw error;}return value;
}
async function adminDrafts(container,feedback,onOrders){
 let filter={page:1,state:'',kind:''},current=null,editing=false,dirty=false,busy=false,requestKey=crypto.randomUUID(),searchSequence=0;
 const fail=error=>{message(feedback,error.message);if(error.status===401){current=null;editing=false;adminClosePrintPreviews();container.innerHTML='<div class="commerce-empty"><h2>로그인이 만료되었습니다.</h2><a class="button-primary" href="/admin.html">다시 로그인</a></div>';}};
 const discard=()=>!dirty||window.confirm('저장하지 않은 견적 내용이 있습니다. 이 내용을 닫을까요?');
 function markDirty(){dirty=true;if(!current)requestKey=crypto.randomUUID();for(const button of container.querySelectorAll('[data-draft-review],[data-draft-print],[data-draft-download]'))button.disabled=true;const hint=container.querySelector('[data-draft-unsaved]');if(hint)hint.hidden=false;}
 function saveBlob(blob,name){const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
 async function quote(download){
  if(busy||dirty||!current)return;busy=true;container.setAttribute('aria-busy','true');
  try{const response=await fetch('/api/orders?'+new URLSearchParams({action:'admin-draft-quote',id:current.id}),{credentials:'same-origin',cache:'no-store'});if(!response.ok){const value=await response.json();const error=Error(value.error||'견적을 준비하지 못했습니다.');error.status=response.status;throw error;}const html=await response.text();if(download)saveBlob(new Blob([html],{type:'text/html;charset=utf-8'}),'nadaun-quote-'+current.id+'.html');else adminOpenPrintPreview(html,adminDraftStates[current.state],text=>message(feedback,text));}catch(error){fail(error);}finally{busy=false;container.removeAttribute('aria-busy');}
 }
 async function change(action,body){
  if(busy)return;busy=true;container.setAttribute('aria-busy','true');
  try{const result=await api(action,body);current=result.draft;editing=true;dirty=false;await list();message(feedback,action==='admin-draft-review'?'견적 입력 검토를 완료했습니다. 실제 주문·예약은 생성하지 않았습니다.':action==='admin-draft-void'?'견적 초안을 취소했습니다.':'견적 초안을 저장했습니다. 고객에게 전송되지 않습니다.');}catch(error){fail(error);}finally{busy=false;container.removeAttribute('aria-busy');}
 }
 function editor(){
  const host=container.querySelector('[data-draft-editor-host]');if(!editing){host.innerHTML='';return;}searchSequence++;
  const draft=current,readonly=draft?.state==='voided',kind=draft?.kind||'purchase',customer=draft?.customer||{},schedule=draft?.rental||{},rows=(draft?.items||[]).map(r=>({...r}));
  const field=(key,label,type='text',required=false,max=160)=>`<label>${label}<input type="${type}" name="${key}" value="${esc(customer[key]||'')}" maxlength="${max}" ${required?'required':''} ${readonly?'disabled':''}></label>`;
  host.innerHTML=`<section class="commerce-draft-editor"><header><div><span>${draft?esc(adminDraftStates[draft.state]):'새 견적 초안'}</span><h2>${draft?esc(draft.id):'수기 견적 작성'}</h2>${draft?'<p>버전 '+draft.version+' · '+esc(new Date(draft.updated_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))+'</p>':''}</div><button type="button" class="button-outline" data-draft-close>닫기</button></header><p class="commerce-note">${adminDraftNotice}</p>${readonly?'<p class="commerce-note">취소 사유: '+esc(draft.void_reason)+'</p>':''}<form data-draft-editor autocomplete="off"><div class="commerce-draft-grid"><label>견적 유형<select name="kind" ${readonly?'disabled':''}><option value="purchase" ${kind==='purchase'?'selected':''}>상품 구매</option><option value="rental" ${kind==='rental'?'selected':''}>장비 렌탈</option></select></label>${field('name','고객 이름','text',true,60)}${field('phone','연락처','tel',true,20)}${field('email','이메일 (선택)','email',false,254)}${field('postcode','우편번호 (선택)','text',false,5)}${field('address','주소 (선택)')}${field('address_detail','상세 주소 (선택)','text',false,100)}</div><fieldset class="commerce-draft-rental" ${kind==='rental'?'':'hidden'} ${kind==='rental'&&!readonly?'':'disabled'}><legend>대여 일정 · 최대 14일</legend><div class="commerce-draft-grid">${[['start_date','수령일','date'],['pickup_time','수령 시간','time'],['end_date','반납일','date'],['return_time','반납 시간','time']].map(([key,label,type])=>`<label>${label}<input type="${type}" name="${key}" value="${esc(schedule[key]||'')}" required></label>`).join('')}</div><p>단가는 전체 대여 기간의 1개당 요금입니다. 미확정이면 모든 상품의 단가를 비워 초안으로 저장하세요.</p></fieldset>${readonly?'':'<div class="commerce-draft-search"><h3>상품 선택</h3><label>상품명 또는 상품번호<input type="search" data-draft-search maxlength="100" placeholder="예: 카메라, 조명, 상품번호"></label><button type="button" class="button-outline" data-draft-search-button>상품 찾기</button><div data-draft-search-results aria-live="polite"></div></div>'}<div data-draft-lines></div><label class="commerce-draft-note">내부 메모<textarea name="note" rows="3" maxlength="2000" ${readonly?'disabled':''}>${esc(draft?.note||'')}</textarea><small>견적 출력에는 포함되지 않습니다.</small></label>${draft?'<div class="commerce-draft-totals"><span>상품 금액 '+money(draft.subtotal)+'</span><span>'+(kind==='rental'?'방문 수령':'배송비')+' '+money(draft.shipping)+'</span><strong>저장된 합계 '+money(draft.total)+'</strong></div>':'<p class="commerce-note">금액과 배송비는 저장할 때 서버의 현재 상품 정보로 확인합니다.</p>'}<p data-draft-unsaved hidden>수정한 내용을 저장한 뒤 검토·출력하세요.</p><div class="commerce-draft-actions">${readonly?'':'<button class="button-primary">'+(draft?'수정 내용 저장':'초안 저장')+'</button>'}${draft?.state==='draft'?'<button type="button" class="button-outline" data-draft-review>저장 내용 재검증 · 검토 완료</button>':''}${draft&&!readonly?'<button type="button" class="button-outline" data-draft-print>견적 미리보기 · 인쇄</button><button type="button" class="button-outline" data-draft-download>견적 HTML 다운로드</button>':''}</div></form>${draft&&!readonly?'<details class="commerce-draft-cancel"><summary>견적 취소</summary><form data-draft-void><label>취소 사유<textarea name="reason" minlength="2" maxlength="1000" rows="2" required></textarea></label><button class="button-outline">견적 취소 기록</button><p>견적 초안만 취소합니다. 실제 주문이나 결제에는 영향을 주지 않습니다.</p></form></details>':''}</section>`;
  const form=host.querySelector('[data-draft-editor]'),kindInput=form.querySelector('[name=kind]'),lineHost=form.querySelector('[data-draft-lines]');let selectedKind=kind;
  function drawRows(){lineHost.innerHTML=adminDraftRows(rows,selectedKind,readonly);for(const input of lineHost.querySelectorAll('[data-draft-quantity]'))input.oninput=()=>{rows[Number(input.dataset.draftQuantity)].quantity=input.value;markDirty();};for(const input of lineHost.querySelectorAll('[data-draft-price]'))input.oninput=()=>{rows[Number(input.dataset.draftPrice)].unit_price=input.value;markDirty();};for(const button of lineHost.querySelectorAll('[data-draft-remove]'))button.onclick=()=>{rows.splice(Number(button.dataset.draftRemove),1);drawRows();markDirty();};}drawRows();
  host.querySelector('[data-draft-close]').onclick=()=>{if(busy||!discard())return;editing=false;current=null;dirty=false;editor();};
  form.addEventListener('input',event=>{if(!event.target.hasAttribute('data-draft-search'))markDirty();});
  kindInput.onchange=()=>{if(rows.length){kindInput.value=selectedKind;message(feedback,'선택한 상품을 모두 제외한 뒤 구매·렌탈 유형을 바꿔주세요.');return;}selectedKind=kindInput.value;const rental=form.querySelector('.commerce-draft-rental');rental.hidden=selectedKind!=='rental';rental.disabled=selectedKind!=='rental';const results=form.querySelector('[data-draft-search-results]');if(results)results.innerHTML='';searchSequence++;drawRows();markDirty();};
  form.onsubmit=event=>{event.preventDefault();if(readonly||busy)return;try{const input=adminDraftInput(Object.fromEntries(new FormData(form)),rows,draft);if(!draft)input.request_key=requestKey;void change(draft?'admin-draft-update':'admin-draft-create',input);}catch(error){fail(error);}};
  const review=host.querySelector('[data-draft-review]');if(review)review.onclick=()=>{if(!dirty)void change('admin-draft-review',{id:draft.id,version:draft.version});};
  const print=host.querySelector('[data-draft-print]');if(print)print.onclick=()=>quote(false);const download=host.querySelector('[data-draft-download]');if(download)download.onclick=()=>quote(true);
  const cancel=host.querySelector('[data-draft-void]');if(cancel)cancel.onsubmit=event=>{event.preventDefault();void change('admin-draft-void',{id:draft.id,version:draft.version,reason:new FormData(cancel).get('reason')});};
  if(readonly)return;
  const search=form.querySelector('[data-draft-search]'),searchButton=form.querySelector('[data-draft-search-button]'),results=form.querySelector('[data-draft-search-results]');
  async function findProducts(){const sequence=++searchSequence;searchButton.disabled=true;results.textContent='상품을 찾고 있습니다.';try{const result=await adminGet('admin-draft-products',{kind:selectedKind,q:search.value.trim()});if(sequence!==searchSequence||!form.isConnected)return;results.innerHTML='<p>검색 결과 '+Number(result.total||0).toLocaleString('ko-KR')+'개 · 최대 20개 표시</p>'+adminDraftProducts(result.products);for(const button of results.querySelectorAll('[data-draft-add]'))button.onclick=()=>{const index=Number(button.dataset.draftAdd),p=result.products[index],option=results.querySelector('[data-draft-option="'+index+'"]')?.value||'',existing=rows.find(r=>r.id===p.id&&r.option===option);if(existing){if(Number(existing.quantity)>=99){message(feedback,'같은 상품은 최대 99개까지 입력할 수 있습니다.');return;}existing.quantity=Number(existing.quantity)+1;}else{if(rows.length>=30){message(feedback,'상품 구성은 최대 30개까지 추가할 수 있습니다.');return;}rows.push({id:p.id,name:p.name,option,quantity:1,unit_price:selectedKind==='rental'?null:p.price});}drawRows();markDirty();message(feedback,'견적에 상품을 추가했습니다. 저장할 때 현재 가격과 상태를 확인합니다.');};}catch(error){if(sequence===searchSequence)results.textContent=error.message;fail(error);}finally{if(sequence===searchSequence)searchButton.disabled=false;}}
  searchButton.onclick=()=>void findProducts();search.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();void findProducts();}};
 }
 async function list(){
  const result=await adminGet('admin-drafts',filter);
  container.innerHTML=`<div class="commerce-admin-tools"><div><strong>수기 견적</strong><span>내부 초안·견적만 관리합니다.</span></div><button type="button" class="button-outline" data-orders-workspace>주문 작업실</button><button type="button" class="button-outline" data-draft-logout>로그아웃</button></div><p class="commerce-draft-notice">${adminDraftNotice}</p><form class="commerce-draft-list-filter"><label>유형<select name="kind"><option value="">구매·렌탈 전체</option><option value="purchase" ${filter.kind==='purchase'?'selected':''}>구매</option><option value="rental" ${filter.kind==='rental'?'selected':''}>렌탈</option></select></label><label>상태<select name="state"><option value="">전체 견적</option>${Object.entries(adminDraftStates).map(([key,label])=>'<option value="'+key+'" '+(filter.state===key?'selected':'')+'>'+label+'</option>').join('')}</select></label><button class="button-outline">조회하기</button><button type="button" class="button-primary" data-draft-new>새 견적 초안</button></form><div data-draft-editor-host></div><div class="commerce-result-heading"><h2>견적 ${Number(result.total).toLocaleString('ko-KR')}건</h2><p>실제 주문 수와 분리됩니다.</p></div><div class="commerce-draft-list">${result.drafts.length?result.drafts.map(d=>`<article><div><span>${esc(adminDraftStates[d.state])} · ${d.kind==='rental'?'렌탈':'구매'}</span><strong>${esc(d.customer.name)}</strong><small>${esc(d.id)}</small><small>${esc(new Date(d.updated_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))}</small></div><div><p>${esc(d.items[0]?.name||'상품 확인')}${d.items.length>1?' 외 '+(d.items.length-1)+'종':''}</p><strong>${money(d.total)}</strong></div><button type="button" class="button-outline" data-draft-open="${esc(d.id)}">상세 · 수정</button></article>`).join(''):'<div class="commerce-empty"><h2>저장된 견적이 없습니다.</h2><p>새 견적 초안에서 고객과 상품을 입력하세요.</p></div>'}</div><nav class="commerce-admin-pages"><button type="button" class="button-outline" data-draft-prev ${result.page<=1?'disabled':''}>← 이전</button><span>${result.page} / ${result.pages} 페이지</span><button type="button" class="button-outline" data-draft-next ${result.page>=result.pages?'disabled':''}>다음 →</button></nav>`;
  container.querySelector('[data-orders-workspace]').onclick=()=>{if(!busy&&discard()){adminClosePrintPreviews();current=null;editing=false;dirty=false;onOrders();}};
  container.querySelector('[data-draft-logout]').onclick=async()=>{if(busy||!discard())return;try{await api('logout',{});adminClosePrintPreviews();container.innerHTML='';location.reload();}catch(error){fail(error);}};
  const form=container.querySelector('.commerce-draft-list-filter');form.onsubmit=event=>{event.preventDefault();if(busy||!discard())return;filter={...Object.fromEntries(new FormData(form)),page:1};editing=false;current=null;dirty=false;void list().catch(fail);};
  container.querySelector('[data-draft-new]').onclick=()=>{if(busy||!discard())return;current=null;editing=true;dirty=false;requestKey=crypto.randomUUID();editor();};
  for(const button of container.querySelectorAll('[data-draft-open]'))button.onclick=async()=>{if(busy||!discard())return;busy=true;button.disabled=true;try{const value=await adminGet('admin-draft',{id:button.dataset.draftOpen});current=value.draft;editing=true;dirty=false;editor();}catch(error){fail(error);}finally{busy=false;button.disabled=false;}};
  for(const [selector,delta]of [['[data-draft-prev]',-1],['[data-draft-next]',1]])container.querySelector(selector).onclick=()=>{if(busy||!discard())return;filter.page+=delta;editing=false;current=null;dirty=false;void list().catch(fail);};
  editor();
 }
 await list().catch(fail);
}

async function admin(){
 if(location.hostname==='order.nadaun.co')for(const link of document.querySelectorAll('a[href^="/"]')){const href=link.getAttribute('href');if(!href.startsWith('/#'))link.href='https://shop.nadaun.co'+href;}
 const container=main.querySelector('#commerce-content'),feedback=main.querySelector('#commerce-status');
 const year=new Date(Date.now()+9*3600000).getUTCFullYear();
 const reset={state:'',fulfillment:'',document:'',kind:'',queue:''};
 let filters={from:year+'-01-01',to:year+'-12-31',basis:'created',mode:commerceTesting?'all':'operational',...reset,search:'',searchField:'all',page:1},busy=false,readiness,expandedId='',selectedTab='all';
 const linkedOrder=new URLSearchParams(location.search).get('order');
 if(linkedOrder&&/^NS-[a-zA-Z0-9_-]{1,40}$/.test(linkedOrder)){try{const linked=await adminGet('admin-order',{id:linkedOrder}),at=new Date(linked.order.created_at+9*3600000).toISOString().slice(0,10);filters={...filters,from:at,to:at,search:linkedOrder,searchField:'order'};expandedId=linkedOrder;}catch{}}
 const options=(rows,selected)=>rows.map(([value,label])=>`<option value="${esc(value)}" ${selected===value?'selected':''}>${esc(label)}</option>`).join('');
 const params=()=>new URLSearchParams(Object.entries(filters).map(([k,v])=>[k,String(v)]));
 const selected=new Set();let currentOrders=[],preferences=adminReadPreferences(),actionBusy=false,invoiceState=null,shippingStatus=null,shippingPreview=null;
 const selectedOrders=()=>currentOrders.filter(o=>selected.has(o.id));
 function clearShippingPreview(){shippingPreview=null;const result=container.querySelector('[data-label-result]');if(result)result.innerHTML='';}
 function clearSelection(){selected.clear();expandedId='';clearShippingPreview();}
 function savePreferences(){preferences=adminSavePreferences(preferences);}
 function syncSelection(){
  const rows=selectedOrders(),count=rows.length;
  for(const input of container.querySelectorAll('[data-select-order]')){input.checked=selected.has(input.dataset.selectOrder);input.closest('tr').classList.toggle('is-selected',input.checked);}
  const all=container.querySelector('[data-select-page]');if(all){all.checked=!!currentOrders.length&&count===currentOrders.length;all.indeterminate=count>0&&count<currentOrders.length;}
  const label=container.querySelector('[data-selection-count]');if(label)label.textContent=count.toLocaleString('ko-KR');
  for(const button of container.querySelectorAll('[data-selected-export],[data-print-orders],[data-clear-selection],[data-invoice-selected-template]'))button.disabled=!count;
  for(const button of container.querySelectorAll('[data-label-preview],[data-label-sync],[data-label-print]'))button.disabled=!count||count>25||actionBusy;
  const bulk=container.querySelector('[data-bulk-workflow]');if(bulk)bulk.disabled=!count||count>25;
 }
 function syncView(){
  const view=container.querySelector('[data-admin-layout]');if(view){view.dataset.adminLayout=preferences.layout;view.dataset.adminDensity=preferences.density;for(const cell of view.querySelectorAll('[data-column]'))cell.hidden=!preferences.columns.includes(cell.dataset.column);for(const td of view.querySelectorAll('.commerce-detail-row>td'))td.colSpan=preferences.columns.length+2;}
 }
 function saveBlob(blob,name){const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
 function printSelection(kind){
  const orders=selectedOrders();if(!orders.length)return;
  const title=kind==='statement'?'거래명세서':'주문서';
  adminOpenPrintPreview('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>'+title+'</title><link rel="stylesheet" href="/assets/shop/shop.css"><link rel="stylesheet" href="/assets/shop/commerce.css"></head><body>'+adminPrintDocument(orders,kind)+'</body></html>',title,error=>message(feedback,error));
 }
 async function download(format,button,onlySelected=false){
  const rows=selectedOrders();if(onlySelected&&!rows.length)return;
  button.disabled=true;message(feedback,onlySelected?'선택한 주문을 파일로 준비하고 있습니다.':'전체 조회 결과를 파일로 준비하고 있습니다.');
  try{
   const response=await fetch('/api/orders?action=admin-export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filters,format,...(onlySelected?{ids:rows.map(o=>o.id)}:{})}),credentials:'same-origin',cache:'no-store'});
   if(!response.ok){const value=await response.json();throw Error(value.error||'자료 다운로드를 확인해주세요.');}
   saveBlob(await response.blob(),'nadaun-'+(onlySelected?'selected-':'')+'orders-'+filters.from+'_'+filters.to+'.'+format);message(feedback,onlySelected?rows.length+'건의 선택 주문을 다운로드했습니다.':'조회 조건에 해당하는 전체 자료를 다운로드했습니다.');
  }catch(error){message(feedback,error.message);}finally{button.disabled=false;syncSelection();}
 }
 function bindWorkspace(){
  for(const input of container.querySelectorAll('[data-select-order]'))input.onchange=()=>{clearShippingPreview();if(input.checked)selected.add(input.dataset.selectOrder);else selected.delete(input.dataset.selectOrder);syncSelection();};
  const all=container.querySelector('[data-select-page]');if(all)all.onchange=()=>{clearShippingPreview();for(const o of currentOrders)if(all.checked)selected.add(o.id);else selected.delete(o.id);syncSelection();};
  container.querySelector('[data-clear-selection]').onclick=()=>{clearSelection();syncSelection();};
  for(const button of container.querySelectorAll('[data-selected-export]'))button.onclick=()=>download(button.dataset.selectedExport,button,true);
  for(const button of container.querySelectorAll('[data-print-orders]'))button.onclick=()=>printSelection(button.dataset.printOrders);
  for(const input of container.querySelectorAll('[data-admin-column]'))input.onchange=()=>{preferences.columns=[...container.querySelectorAll('[data-admin-column]:checked')].map(i=>i.dataset.adminColumn);savePreferences();syncView();};
  for(const input of container.querySelectorAll('[name=admin-layout],[name=admin-density]'))input.onchange=()=>{preferences[input.name==='admin-layout'?'layout':'density']=input.value;savePreferences();syncView();};
  container.querySelector('[data-view-reset]').onclick=()=>{preferences={...adminPreferences(),presets:preferences.presets,filtersOpen:preferences.filtersOpen};savePreferences();syncView();for(const input of container.querySelectorAll('[data-admin-column]'))input.checked=true;for(const input of container.querySelectorAll('[name=admin-layout],[name=admin-density]'))input.checked=input.value===(input.name==='admin-layout'?preferences.layout:preferences.density);};
  const filterSection=container.querySelector('[data-admin-filters]');filterSection.ontoggle=()=>{preferences.filtersOpen=filterSection.open;savePreferences();};
  const presetSelect=container.querySelector('[data-filter-preset]');
  container.querySelector('[data-preset-save]').onclick=()=>{const preset=adminFilterMetadata(filters),same=p=>JSON.stringify(p)===JSON.stringify(preset);preferences.presets=[preset,...preferences.presets.filter(p=>!same(p))].slice(0,8);savePreferences();presetSelect.innerHTML='<option value="">조건 선택</option>'+preferences.presets.map((p,i)=>'<option value="'+i+'">'+esc(adminPresetTitle(p))+'</option>').join('');message(feedback,'현재 조회 조건을 저장했습니다. 검색어는 저장하지 않습니다.');};
  container.querySelector('[data-preset-delete]').onclick=()=>{if(presetSelect.value==='')return;preferences.presets.splice(Number(presetSelect.value),1);savePreferences();presetSelect.selectedOptions[0].remove();[...presetSelect.options].forEach((o,i)=>{if(i)o.value=String(i-1);});presetSelect.value='';};
  container.querySelector('[data-preset-apply]').onclick=()=>{if(presetSelect.value==='')return;const preset=preferences.presets[Number(presetSelect.value)];if(!preset)return;filters={...filters,...reset,...preset,search:'',page:1};selectedTab='custom';clearSelection();void refresh();};
  const stageSelect=container.querySelector('[data-bulk-stage]'),confirm=container.querySelector('[data-bulk-confirm]');
  stageSelect.onchange=()=>{confirm.closest('label').hidden=stageSelect.value!=='delivered';confirm.checked=false;};
  container.querySelector('[data-bulk-workflow]').onclick=async event=>{
   const rows=selectedOrders();if(actionBusy||!rows.length||rows.length>25)return;
   if(stageSelect.value==='delivered'&&!confirm.checked){message(feedback,'선택한 주문의 전체 상품 수령을 확인한 뒤 체크해주세요.');return;}
   actionBusy=true;event.currentTarget.disabled=true;container.setAttribute('aria-busy','true');
   try{const result=await api('admin-workflow-bulk',{stage:stageSelect.value,orders:rows.map(o=>({id:o.id,version:o.version}))});selected.clear();for(const r of result.results||[])if(!r.ok)selected.add(r.id);actionBusy=false;await list();message(feedback,`배송 단계 저장 ${result.succeeded}건 / 미처리 ${result.failed}건`+(result.failed?' · '+result.results.filter(r=>!r.ok).map(r=>r.id+': '+r.error).join(' / '):''));}catch(error){message(feedback,error.message);}finally{actionBusy=false;container.removeAttribute('aria-busy');syncSelection();}
  };
  bindInvoice();bindShipping();syncSelection();
 }
 function bindShipping(){
  const panel=container.querySelector('[data-auto-shipping]');if(!shippingStatus?.enabled||!panel)return;
  const contract=panel.querySelector('[data-label-contract]'),box=panel.querySelector('[data-label-box]'),result=panel.querySelector('[data-label-result]');
  const show=()=>{
   if(!shippingPreview){result.innerHTML='';return;}
   const p=shippingPreview;
   result.innerHTML='<h3>접수 전 확인 · '+esc(p.carrier)+' / '+esc(p.box)+'</h3><ul>'+p.results.map(r=>'<li><strong>'+esc(r.id)+'</strong> '+(r.ok?esc(r.name)+' · '+esc(r.address)+' · '+r.quantity+'개':esc(r.error))+(r.outcome?' — '+esc(r.outcome):'')+'</li>').join('')+'</ul>'+(p.results.some(r=>r.ok&&!r.outcome)?'<label class="commerce-check"><input type="checkbox" data-label-confirm><span>배송 정보·박스 규격을 확인했으며 선택 주문을 택배 접수합니다.</span></label><button class="button-primary" data-label-register>확인한 주문 접수</button>':'');
   const button=result.querySelector('[data-label-register]');if(!button)return;
   button.onclick=async()=>{
    if(actionBusy||!result.querySelector('[data-label-confirm]').checked){message(feedback,'배송 정보와 규격을 확인한 뒤 체크해주세요.');return;}
    actionBusy=true;button.disabled=true;
    try{for(const r of p.results.filter(r=>r.ok&&!r.outcome)){
      try{await api('admin-label-register',{id:r.id,version:r.version,contract_id:p.contract_id,box:p.box,confirmed:true});r.outcome='접수 완료 · 인쇄 전';}
      catch(error){r.outcome=error.message+' · 송장 조회로 확인';break;}
     }
    }finally{actionBusy=false;await refresh();}
   };
  };
  contract.onchange=()=>{const c=shippingStatus.contracts.find(c=>c.id===contract.value);box.innerHTML='<option value="">박스 규격 선택</option>'+(c?.boxes||[]).map(b=>'<option value="'+esc(b.code)+'">'+esc(b.name+' ('+b.code+')')+'</option>').join('');shippingPreview=null;show();};
  box.onchange=()=>{shippingPreview=null;show();};
  panel.querySelector('[data-label-preview]').onclick=async()=>{
   if(actionBusy)return;if(!contract.value||!box.value){message(feedback,'택배 계약과 박스 규격을 선택해주세요.');return;}
   actionBusy=true;syncSelection();
   try{shippingPreview=await api('admin-label-preview',{orders:selectedOrders().map(o=>({id:o.id,version:o.version})),contract_id:contract.value,box:box.value});show();}
   catch(error){message(feedback,error.message);}finally{actionBusy=false;syncSelection();}
  };
  panel.querySelector('[data-label-sync]').onclick=async()=>{
   if(actionBusy)return;actionBusy=true;syncSelection();const errors=[];
   try{for(const o of selectedOrders()){try{await api('admin-label-sync',{id:o.id});}catch(error){errors.push(o.id+': '+error.message);}}}
   finally{actionBusy=false;await refresh();message(feedback,errors.length?errors.join(' / '):'발급 번호와 배송 상태를 조회했습니다.');}
  };
  panel.querySelector('[data-label-print]').onclick=async()=>{
   if(actionBusy)return;
   const ids=selectedOrders().map(o=>o.id),include_printed=panel.querySelector('[data-label-reprint]').checked;
   const popup=window.open('about:blank','platform-print-window-target-name');if(!popup){message(feedback,'송장 인쇄를 위해 팝업을 허용해주세요.');return;}popup.opener=null;
   actionBusy=true;syncSelection();
   try{const value=await api('admin-label-print',{ids,include_printed}),url=new URL(value.uri);if(url.protocol!=='https:'||url.hostname!=='admin.goodsflow.io'||url.port||url.username||url.password||!url.pathname.startsWith('/invoice-print/public/print/'))throw Error('인쇄 주소를 확인해주세요.');popup.location.replace(url.href);message(feedback,'굿스플로 인쇄 창을 열었습니다. 인쇄 후 발급된 번호를 자동 조회합니다.');}
   catch(error){popup.close();message(feedback,error.message);}finally{actionBusy=false;syncSelection();}
  };
  if(shippingPreview){panel.open=true;contract.value=shippingPreview.contract_id;const c=shippingStatus.contracts.find(c=>c.id===contract.value);box.innerHTML=(c?.boxes||[]).map(b=>'<option value="'+esc(b.code)+'">'+esc(b.name)+'</option>').join('');box.value=shippingPreview.box;}show();
 }

 function bindInvoice(){
  const resultArea=container.querySelector('[data-invoice-result]'),form=container.querySelector('[data-invoice-upload]');
  for(const button of container.querySelectorAll('[data-invoice-template],[data-invoice-selected-template]'))button.onclick=()=>saveBlob(new Blob([adminInvoiceTemplate(button.hasAttribute('data-invoice-selected-template')?selectedOrders():[])],{type:'text/csv;charset=utf-8'}),'nadaun-invoice-template.csv');
  function show(){
   if(!invoiceState){resultArea.innerHTML='';return;}
   resultArea.innerHTML=adminInvoicePreviewMarkup(invoiceState.preview,invoiceState.outcomes);const button=resultArea.querySelector('[data-invoice-apply]');if(!button)return;
   const pending=invoiceState.preview.operations.filter(op=>!invoiceState.outcomes[op.index]?.ok);
   button.disabled=!pending.length||invoiceState.running;button.textContent=!pending.length?'전체 처리 완료':Object.keys(invoiceState.outcomes).length?'미완료 송장 재시도':'검증한 송장 등록';
   button.onclick=async()=>{
    if(actionBusy||invoiceState.running||!resultArea.querySelector('[data-invoice-confirm]').checked){message(feedback,'검증 결과의 주문·송장·수량을 확인한 뒤 체크해주세요.');return;}
    if(invoiceState.preview.expires_at&&new Date(invoiceState.preview.expires_at).getTime()<Date.now()){message(feedback,'검증 유효시간이 지났습니다. 파일을 다시 검증해주세요.');return;}
    actionBusy=true;invoiceState.running=true;container.setAttribute('aria-busy','true');button.disabled=true;
    try{for(const op of pending){
      try{const r=await api('admin-invoice-apply',{preview_token:invoiceState.preview.preview_token,index:op.index});invoiceState.outcomes[op.index]={ok:true,duplicate:!!r.duplicate};}
      catch(error){invoiceState.outcomes[op.index]={ok:false,error:error.message};break;}
      const cell=resultArea.querySelector('[data-invoice-outcome="'+op.index+'"]');if(cell)cell.textContent=invoiceState.outcomes[op.index].duplicate?'기존 처리 확인':'처리 완료';
     }
    }finally{invoiceState.running=false;actionBusy=false;container.removeAttribute('aria-busy');}
    const successes=Object.values(invoiceState.outcomes).filter(r=>r.ok).length,total=invoiceState.preview.operations.length;
    await refresh();message(feedback,`송장 처리 ${successes}/${total}건 완료`+(successes<total?' · 중단된 결과를 확인하고 미완료 작업만 재시도하세요.':''));
   };
  }
  form.onsubmit=async event=>{
   event.preventDefault();if(actionBusy)return;const file=form.querySelector('[type=file]').files[0];if(!file)return;
   if(!/\.(csv|xlsx)$/i.test(file.name)||file.size>1048576){message(feedback,'1MiB 이하의 CSV 또는 XLSX 파일을 선택해주세요.');return;}
   const button=form.querySelector('button');button.disabled=true;actionBusy=true;container.setAttribute('aria-busy','true');invoiceState=null;show();
   try{const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let offset=0;offset<bytes.length;offset+=8192)binary+=String.fromCharCode(...bytes.subarray(offset,offset+8192));
    const preview=await api('admin-invoice-preview',{filename:file.name,file_base64:btoa(binary)});invoiceState={preview,outcomes:{},running:false};show();message(feedback,preview.valid?'파일 검증이 완료됐습니다. 실행 전 내용을 확인하세요.':'파일 오류를 확인해주세요. 아직 송장을 등록하지 않았습니다.');
   }catch(error){message(feedback,error.message);}finally{actionBusy=false;container.removeAttribute('aria-busy');button.disabled=false;form.reset();}
  };show();
 }
 const refresh=()=>{if(actionBusy){message(feedback,'진행 중인 주문 처리가 끝난 뒤 다시 조회해주세요.');return Promise.resolve();}return list().catch(error=>{if(error.status===401){selected.clear();currentOrders=[];invoiceState=null;shippingPreview=null;shippingStatus=null;adminClosePrintPreviews();container.innerHTML='<div class="commerce-empty"><h2>로그인이 만료되었습니다.</h2><a class="button-primary" href="/admin.html">다시 로그인</a></div>';}message(feedback,error.status===401?'로그인이 만료되었습니다. 다시 로그인해주세요.':error.message);});};
 async function list(){
  if(busy)return;busy=true;container.setAttribute('aria-busy','true');
  try{
   const response=await fetch('/api/orders?action=admin-orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filters}),credentials:'same-origin',cache:'no-store'}),value=await response.json();
   if(!response.ok){const error=Error(value.error||'주문을 확인하지 못했습니다.');error.status=response.status;throw error;}
   let health=null;try{const response=await fetch('/api/orders?action=admin-calendar-health',{credentials:'same-origin',cache:'no-store'});if(response.ok)health=(await response.json()).calendar;}catch{}
   try{shippingStatus=await api('admin-label-status');}catch(error){shippingStatus={enabled:false,message:error.message};}
   currentOrders=value.orders;for(const id of selected)if(!currentOrders.some(o=>o.id===id))selected.delete(id);
   const s=value.summary,w=value.workload||s;
   const calendarStatus=health?.status==='connected'&&Date.now()-health.checked_at<180000?'캘린더 연결 확인':health?'캘린더 연결 점검 필요':'캘린더 연결 확인 중';
   const pg=readiness.paymentProvider==='toss'?'<a href="https://app.tosspayments.com/" target="_blank" rel="noopener noreferrer">결제사 거래·환불 관리 ↗</a>':'';
   container.innerHTML=`<div class="commerce-admin-tools"><div><strong>주문 작업실</strong><span>마지막 조회 ${esc(new Date().toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul'}))}</span></div><a class="button-outline" href="/members-admin.html">고객관리</a><a class="button-outline" href="https://shop.nadaun.co/test-shop.html">전체 구매 테스트</a><button class="button-outline" data-open-drafts>수기 견적</button><button class="button-outline" data-refresh>새로고침</button><button class="button-outline" data-logout>로그아웃</button></div><nav class="commerce-work-tabs" aria-label="처리할 주문">${adminTabs.map(tab=>`<button type="button" data-worktab="${tab.id}" aria-pressed="${selectedTab===tab.id}"><span>${tab.label}</span>${Number.isFinite(w[tab.count])?'<strong>'+w[tab.count].toLocaleString('ko-KR')+'</strong>':''}</button>`).join('')}</nav><details class="commerce-filter-section" data-admin-filters ${preferences.filtersOpen?'open':''}><summary>조회 조건 <span>${esc(filters.from)} — ${esc(filters.to)}</span></summary>${adminPresetControls(preferences)}<form class="commerce-admin-filter"><label>시작일<input type="date" name="from" value="${esc(filters.from)}" required></label><label>종료일<input type="date" name="to" value="${esc(filters.to)}" required></label><label>기간 기준<select name="basis">${options([['created','주문접수일'],['paid','결제확정일']],filters.basis)}</select></label><label>주문 유형<select name="kind">${options([['','구매·렌탈 전체'],['purchase','구매'],['rental','렌탈']],filters.kind)}</select></label><label>주문 상태<select name="state">${options([['','전체'],...Object.entries(states)],filters.state)}</select></label><label>배송·렌탈 처리<select name="fulfillment">${options([['','전체'],['unfulfilled','출고·수령 예정'],['processing','처리 중·대여 중'],['shipped','출고·반납 완료']],filters.fulfillment)}</select></label><label>결제 환경<select name="mode">${options([['operational','운영 주문 (테스트 제외)'],['live','실결제 주문'],['test','테스트 주문'],['all','전체']],filters.mode)}</select></label><label>증빙<select name="document">${options([['','전체'],['queued','발급 대기'],['processing','발급 확인 중'],['issued','발급 완료'],['retry','재확인 중'],['review','확인 필요'],['voided','취소'],['missing','미발급']],filters.document)}</select></label><label>검색 범위<select name="searchField">${options([['all','전체'],['order','주문번호·결제 거래번호'],['customer','고객 이름·연락처'],['tracking','운송장번호']],filters.searchField)}</select></label><label class="commerce-admin-search">주문 · 고객 · 송장 검색<input type="search" name="search" value="${esc(filters.search)}" maxlength="80" placeholder="주문번호, 고객 이름·전화번호, 송장번호"></label><div class="commerce-admin-filter-actions"><button class="button-primary">조회하기</button><button type="button" class="button-outline" data-days="7">최근 7일</button><button type="button" class="button-outline" data-days="30">최근 30일</button><button type="button" class="button-outline" data-year>올해 결제 자료</button><button type="button" class="button-outline" data-last-year>작년 결제 자료</button></div></form></details><div class="commerce-result-heading"><div><h2>조회 결과 <strong>${s.orders.toLocaleString('ko-KR')}</strong></h2><p>${esc(filters.from)} — ${esc(filters.to)} · ${selectedTab==='custom'?'상세 조건':adminTabs.find(t=>t.id===selectedTab)?.label||'전체 주문'}</p></div><div>${adminViewControls(preferences)}<button class="button-outline" data-export="xlsx">전체 조회 엑셀</button><button class="button-outline" data-export="csv">CSV</button></div></div><section class="commerce-selection-tools" aria-label="선택 주문 작업"><div><strong>선택 <span data-selection-count>0</span>건</strong><span>현재 페이지에서 선택 · 조회 조건이나 페이지를 바꾸면 해제됩니다.</span></div><div class="commerce-selection-actions"><button type="button" class="button-outline" data-selected-export="xlsx" disabled>선택 엑셀</button><button type="button" class="button-outline" data-selected-export="csv" disabled>선택 CSV</button><button type="button" class="button-outline" data-print-orders="order" disabled>주문서 인쇄</button><button type="button" class="button-outline" data-print-orders="statement" disabled>거래명세서 인쇄</button><button type="button" class="button-outline" data-clear-selection disabled>선택 해제</button></div><div class="commerce-bulk-workflow"><label>선택 주문 배송 단계<select data-bulk-stage><option value="preparing">상품 준비</option><option value="ready">배송 대기</option><option value="delivered">배송 완료 · 고객 수령 확인</option></select></label><label class="commerce-check" hidden><input type="checkbox" data-bulk-confirm><span>선택 주문 전체 상품의 고객 수령을 확인했습니다.</span></label><button type="button" class="button-outline" data-bulk-workflow disabled>선택 단계 저장</button><span>최대 25주문 · 적용할 수 없는 주문은 사유를 안내합니다.</span></div></section>${adminTable(value.orders,expandedId,preferences,selected)}<nav class="commerce-admin-pages" aria-label="주문 페이지"><button class="button-outline" data-prev ${value.page<=1?'disabled':''}>← 이전</button><span>${value.page} / ${value.pages} 페이지 · 페이지당 ${value.pageSize}건</span><button class="button-outline" data-next ${value.page>=value.pages?'disabled':''}>다음 →</button></nav>${adminShippingPanel(shippingStatus)}${adminInvoicePanel()}<details class="commerce-admin-connection"><summary>운영 연결 · 결제 · 자료 집계</summary>${adminReadiness(readiness)}<p class="commerce-calendar">${esc(calendarStatus)}</p><div class="commerce-admin-tools">${pg}<span>기프트는 수량·인쇄·납기 상담 후 진행합니다.</span></div><div class="commerce-admin-summary"><div><span>조회 주문의 실결제 원 승인 누계</span><strong>${money(s.approvedTotal)}</strong></div><div><span>취소 주문의 원 승인액</span><strong>${money(s.canceledOriginalTotal)}</strong></div><div><span>증빙 대기·확인</span><strong>${s.documentPending}건</strong></div></div><div class="commerce-admin-notes">${value.notices.map(n=>'<p>'+esc(n)+'</p>').join('')}</div></details>`;
   container.querySelector('[data-refresh]').onclick=refresh;
   container.querySelector('[data-open-drafts]').onclick=()=>{if(actionBusy)return;clearSelection();void adminDrafts(container,feedback,()=>void refresh());};
   container.querySelector('[data-logout]').onclick=async()=>{try{await api('logout',{});selected.clear();currentOrders=[];invoiceState=null;shippingPreview=null;shippingStatus=null;adminClosePrintPreviews();container.innerHTML='';location.reload();}catch(error){message(feedback,error.message);}};
   const filterForm=container.querySelector('.commerce-admin-filter');
   filterForm.onsubmit=event=>{event.preventDefault();filters={...reset,...Object.fromEntries(new FormData(filterForm)),queue:'',page:1};selectedTab='custom';clearSelection();void refresh();};
   for(const button of container.querySelectorAll('[data-worktab]'))button.onclick=()=>{const tab=adminTabs.find(t=>t.id===button.dataset.worktab);filters={...filters,...reset,...tab.filter,page:1};selectedTab=tab.id;clearSelection();void refresh();};
   function annual(y){filters={from:y+'-01-01',to:y+'-12-31',basis:'paid',mode:'live',...reset,search:'',searchField:'all',page:1};selectedTab='all';clearSelection();void refresh();}
   container.querySelector('[data-year]').onclick=()=>annual(year);container.querySelector('[data-last-year]').onclick=()=>annual(year-1);
   for(const button of container.querySelectorAll('[data-days]'))button.onclick=()=>{const today=Date.now()+9*3600000;filters={...filters,from:new Date(today-(Number(button.dataset.days)-1)*86400000).toISOString().slice(0,10),to:new Date(today).toISOString().slice(0,10),basis:'created',page:1};clearSelection();void refresh();};
   for(const button of container.querySelectorAll('[data-export]'))button.onclick=()=>download(button.dataset.export,button);
   container.querySelector('[data-prev]').onclick=()=>{filters.page--;clearSelection();void refresh();};container.querySelector('[data-next]').onclick=()=>{filters.page++;clearSelection();void refresh();};
   for(const button of container.querySelectorAll('[data-open-order]'))button.onclick=()=>{
    expandedId=expandedId===button.dataset.openOrder?'':button.dataset.openOrder;
    for(const other of container.querySelectorAll('[data-open-order]')){const open=other.dataset.openOrder===expandedId;other.setAttribute('aria-expanded',String(open));other.textContent=open?'닫기':'처리하기';const row=other.closest('tr');row.classList.toggle('is-expanded',open);row.nextElementSibling.hidden=!open;}
   };
   bindWorkspace();
   for(const order of value.orders){
    const card=document.getElementById(order.id),status=card.querySelector('.commerce-feedback');
    const history=card.querySelector('.commerce-history');history.ontoggle=async()=>{if(!history.open||history.dataset.loaded)return;const target=history.querySelector('[data-history]');try{const result=await fetch('/api/orders?action=admin-events&id='+encodeURIComponent(order.id),{credentials:'same-origin',cache:'no-store'}),data=await result.json();if(!result.ok)throw Error(data.error||'처리 이력을 확인하지 못했습니다.');const actions={shipping_label_requested:'택배 접수 요청',shipping_label_registered:'택배 접수 확인',shipping_label_synced:'송장·배송 상태 조회',shipping_label_delivered:'택배사 배송 완료 확인',purchase_preparing:'상품 준비',purchase_ready:'배송 대기',purchase_delivered:'관리자 고객 수령 확인',order_requested:'주문 접수',admin_note_updated:'담당자 메모 저장',request_canceled:'미결제 접수 취소',admin_note_cleared:'담당자 메모 지움',rental_picked_up:'방문 수령 완료',rental_returned:'방문 반납 완료',quote_approved:'재고·납기 확인 / 금액 확정',payment_started:'결제 시작',payment_confirming:'결제 승인 요청',payment_done:'결제 승인 저장',payment_canceled:'전체 취소 확인',payment_partial_canceled:'부분 취소 확인',payment_net_canceled:'승인 복구 취소',payment_review:'결제 확인 필요',order_shipped:'전체 출고 완료',order_partially_shipped:'일부 상품 출고',order_tracking_updated:'운송정보 수정',return_case_created:'반품 접수',exchange_case_created:'교환 접수',case_approved:'반품·교환 승인',case_returning:'상품 회수 진행',case_received:'상품 회수 확인',case_closed:'반품·교환 기록 종결',case_rejected:'반품·교환 접수 거절',exchange_shipped:'교환품 재출고',document_payment_changed:'증빙 처리 중 결제 변경 확인'};target.innerHTML='<ol>'+data.events.map(e=>'<li><time>'+esc(new Date(e.created_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))+'</time> '+esc(actions[e.action]||e.action)+' <small>'+esc(e.actor)+'</small></li>').join('')+'</ol>';history.dataset.loaded='true';}catch(error){target.textContent=error.message;}};
    async function change(action,body,button){button.disabled=true;try{await api(action,{id:order.id,version:order.version,...body});await list();message(feedback,'주문 '+order.id+' 처리 내용을 저장했습니다.');}catch(error){message(status,error.message);button.disabled=false;}}
    const workflow=card.querySelector('[data-workflow]');if(workflow)workflow.onsubmit=event=>{event.preventDefault();change('admin-workflow',{stage:new FormData(workflow).get('stage')},workflow.querySelector('button'));};
    const approve=card.querySelector('[data-approve]');if(approve)approve.onclick=()=>{const prices=[...card.querySelectorAll('[data-rental-price]')],giftPrices=[...card.querySelectorAll('[data-gift-price]')],giftShipping=card.querySelector('[data-gift-shipping]');if([...prices,...giftPrices,...(giftShipping?[giftShipping]:[])].some(input=>!input.reportValidity()))return;change('admin-approve',{stock_confirmed:card.querySelector('[data-stock]').checked,...(order.gift?{gift_prices:order.lines.map((line,i)=>({id:line.id,option:line.option,unit_price:Number(giftPrices[i].value)})),gift_shipping:Number(giftShipping.value),gift_conditions_confirmed:card.querySelector('[data-gift-confirmed]').checked}:{}),...(order.kind==='rental'?{rental_prices:order.lines.map((line,i)=>({id:line.id,option:line.option,unit_price:Number(prices[i].value)}))}:{})},approve);};
    for(const [selector,action] of [['[data-rental-pickup]','admin-rental-pickup'],['[data-rental-return]','admin-rental-return'],['[data-reconcile]','admin-reconcile'],['[data-document-retry]','admin-document-retry'],['[data-qa-deliver]','admin-qa-deliver'],['[data-qa-cancel]','admin-qa-cancel']]){const button=card.querySelector(selector);if(button)button.onclick=()=>change(action,{},button);}
    function quantities(form,items){return [...form.querySelectorAll('[data-item-index]')].map(input=>({id:items[Number(input.dataset.itemIndex)].id,option:items[Number(input.dataset.itemIndex)].option||'',quantity:Number(input.value)})).filter(line=>line.quantity>0);}
    function bindQuantity(form,action,items,extra={}){if(!form)return;form.onsubmit=event=>{event.preventDefault();const selected=quantities(form,items);if(!selected.length){message(status,'처리할 수량을 1개 이상 선택해주세요.');return;}change(action,{...Object.fromEntries(new FormData(form)),...extra,items:selected},form.querySelector('button'));};}
    bindQuantity(card.querySelector('[data-shipment-create]'),'admin-ship',remainingShipmentItems(order));
    for(const form of card.querySelectorAll('[data-shipment-update]'))form.onsubmit=event=>{event.preventDefault();change('admin-shipment-update',{...Object.fromEntries(new FormData(form)),shipment_id:form.dataset.shipmentUpdate},form.querySelector('button'));};
    for(const form of card.querySelectorAll('[data-case-create]')){const shipment=originalShipments(order).find(s=>s.id===form.dataset.caseCreate);bindQuantity(form,'admin-case-create',caseRemaining(order,shipment),{shipment_id:shipment.id});}
    for(const form of card.querySelectorAll('[data-case-update]'))form.onsubmit=event=>{event.preventDefault();const body=Object.fromEntries(new FormData(form));if(['closed','rejected'].includes(body.status)&&String(body.note||'').trim().length<2){form.querySelector('[name=note]').setCustomValidity('종결 또는 거절 사유를 2자 이상 입력해주세요.');form.querySelector('[name=note]').reportValidity();form.querySelector('[name=note]').oninput=()=>form.querySelector('[name=note]').setCustomValidity('');return;}for(const key of ['carrier','tracking'])if(!body[key])delete body[key];change('admin-case-update',{...body,case_id:form.dataset.caseUpdate},form.querySelector('button'));};
    for(const form of card.querySelectorAll('[data-exchange-ship]')){const claim=order.admin_cases.find(c=>c.id===form.dataset.exchangeShip);bindQuantity(form,'admin-exchange-ship',claim.replacement_remaining,{case_id:claim.id});}
    for(const [selector,action] of [['[data-admin-note]','admin-note'],['[data-cancel-request]','admin-cancel-request']]){const form=card.querySelector(selector);if(form)form.onsubmit=event=>{event.preventDefault();change(action,Object.fromEntries(new FormData(form)),form.querySelector('button'));};}
   }
  }finally{busy=false;container.setAttribute('aria-busy','false');}
 }
 let labelPolling=false;
 const labelTimer=setInterval(async()=>{
  if(labelPolling||actionBusy||busy||document.hidden||!shippingStatus?.enabled||!container.querySelector('[data-auto-shipping]'))return;
  const pending=currentOrders.filter(o=>o.admin_shipping_label&&!['delivered','review'].includes(o.admin_shipping_label.status));if(!pending.length)return;
  labelPolling=true;try{for(const o of pending.slice(0,2))await api('admin-label-sync',{id:o.id});await refresh();}catch(error){if(error.status===401){clearInterval(labelTimer);void refresh();}}finally{labelPolling=false;}
 },30000);
 window.addEventListener('pagehide',()=>clearInterval(labelTimer),{once:true});
 try{readiness=await config();checkoutPaymentOpen=readiness.ordersEnabled===true;if(!readiness.adminEnabled){container.innerHTML='<div class="commerce-empty"><h2>주문 관리 연결 준비 중</h2><p>주문 저장소와 관리자 인증 설정을 확인해주세요.</p></div>';return;}await list();}
 catch(error){
  if(error.status!==401){message(feedback,error.message);return;}
  container.innerHTML='<div class="commerce-login-layout"><div class="commerce-login-intro"><span class="section-index">NADAUN SPACE / OPERATIONS</span><h2>주문이 들어오면,<br>여기서 이어갑니다.</h2><p>구매의 재고 확인과 출고,<br>렌탈의 수령과 반납을 한곳에서 관리합니다.</p></div><form class="commerce-login"><h2>관리자 로그인</h2>'+(readiness.adminLoginRequiresEmail?'<label>관리자 이메일<input type="email" name="email" autocomplete="username" maxlength="254" required></label>':'')+'<label>관리자 비밀번호<input type="password" name="password" autocomplete="current-password" minlength="16" maxlength="128" required></label><button class="button-primary">로그인 →</button><p class="commerce-note">승인된 관리자만 주문과 고객 정보를 확인할 수 있습니다.</p></form></div>';
  const form=container.querySelector('form');form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('button');button.disabled=true;try{await api('login',Object.fromEntries(new FormData(form)));form.reset();message(feedback,'');await list();}catch(error){message(feedback,error.message);button.disabled=false;}};
 }
}
if(mode==='gift-item')void mountGiftOrder();
else if(mode==='checkout'){document.addEventListener('shop:content-updated',mountCheckout);void mountCheckout();}
else if(mode==='orders')void orders();else if(mode==='admin')void config().then(r=>{commerceTesting=r.testing===true;if(location.pathname==='/test-admin.html'&&!commerceTesting){location.replace('/test-shop.html');return;}return admin();});else if(mode==='payment-test')void paymentTest();
