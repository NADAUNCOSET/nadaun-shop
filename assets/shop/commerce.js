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
const config=()=>configRequest||(configRequest=api('config'));
function message(target,text){target.textContent=text;target.hidden=!text;}
const notice='<p class="commerce-note">이 브라우저에서 접수한 주문을 확인할 수 있습니다. 다른 기기에서 확인하거나 브라우저 데이터를 삭제한 경우에는 주문번호로 고객센터에 문의해주세요.</p>';
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
 return '<fieldset class="commerce-evidence"><legend>결제 방법과 증빙</legend><label>증빙 선택<select name="evidence_kind"><option value="card_receipt">카드 결제 · 카드 매출전표</option><option value="cash_receipt">계좌이체 · 현금영수증 (소득공제 / 지출증빙)</option>'+(taxEnabled?'<option value="tax_invoice">계좌이체 · 전자세금계산서</option>':'')+'</select></label><p class="commerce-note">현금영수증은 이니시스 결제창에서 소득공제 또는 사업자 지출증빙을 선택하고 발급 정보를 입력해주세요. 세금계산서를 선택하면 현금영수증은 함께 발급하지 않습니다.</p>'+(taxEnabled?'':'<p class="commerce-note">전자세금계산서 발급 연결을 준비 중입니다. 필요한 경우 구매 전 상담해주세요.</p>')+'<div class="commerce-fields" data-tax-fields hidden>'+[
  ['corp_num','사업자등록번호 (숫자 10자리)','text',10],['corp_name','상호','text',200],['ceo_name','대표자명','text',100],['address','사업장 주소','text',300],['biz_type','업태','text',100],['biz_class','종목','text',100],['email','세금계산서 수신 이메일','email',100]
 ].map(([key,label,type,max])=>`<label>${label}<input name="tax_${key}" type="${type}" maxlength="${max}" disabled ${key==='corp_num'?'inputmode="numeric" pattern="[0-9]{10}"':''}></label>`).join('')+'</div></fieldset>';
}
function documentCard(doc){
 if(!doc)return '';
 const kind={card_receipt:'카드 매출전표',cash_receipt:doc.purpose==='business'?'현금영수증 · 지출증빙':doc.purpose==='income'?'현금영수증 · 소득공제':'현금영수증',tax_invoice:'전자세금계산서'}[doc.kind]||'결제 증빙';
 const status={queued:'발급 대기',processing:'발급 확인 중',retry:'발급 결과 확인 중',review:'발급 확인 필요',issued:'발급 완료',voided:'취소'}[doc.status]||'확인 중';
 const receipt=typeof doc.receipt_url==='string'&&/^https:\/\/iniweb\.inicis\.com\/DefaultWebApp\/mall\/cr\/cm\/mCmReceipt_head\.jsp\?noTid=[a-zA-Z0-9_-]+&noMethod=1$/.test(doc.receipt_url)?`<p><a href="${esc(doc.receipt_url)}" target="_blank" rel="noopener noreferrer">영수증 조회 · 인쇄 ↗</a></p>`:'';
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
 return `<article class="commerce-order" id="${esc(order.id)}"><header><div><span class="section-index">${esc(order.id)}</span><h2>${order.payment_mode==='test'?'테스트 · ':''}${esc(order.kind==='rental'&&order.state==='REQUESTED'?'대여 일정·요금 확인 중':order.kind==='rental'&&order.state==='APPROVED'&&!checkoutPaymentOpen?'대여 요금 확인 완료':states[order.state]||'상태 확인 필요')}</h2></div><time>${esc(new Date(order.created_at).toLocaleString('ko-KR'))}</time></header><ul class="commerce-lines">${order.lines.map(p=>`<li><a href="/item.html?id=${encodeURIComponent(p.id)}">${esc(p.name)}<small>${esc(p.option||'기본 구성')} · ${p.quantity}개</small></a><strong>${money(p.unit_price===null?null:p.unit_price*p.quantity)}</strong></li>`).join('')}</ul><div class="commerce-totals"><span>${order.kind==='rental'?'전체 기간 대여료 '+money(order.subtotal)+' · 방문 수령':'상품 '+money(order.subtotal)+' + 배송 '+money(order.shipping)}</span><strong>${money(order.total)}</strong></div>${order.kind!=='rental'&&order.fulfillment==='shipped'?`<p class="commerce-shipped">출고 완료 · ${esc(order.carrier)} ${esc(order.tracking)}</p>`:''}${admin&&order.rental&&customer?`<details class="commerce-address"><summary>예약자 정보 확인</summary><p>${esc(customer.name)} · ${esc(customer.phone)}</p></details>`:''}${order.rental?`<dl class="rental-order-schedule"><div><dt>대여 시작일 · 수령 방문</dt><dd>${esc(order.rental.start_date)} ${esc(order.rental.pickup_time)}</dd></div><div><dt>대여 종료일 · 반납 방문</dt><dd>${esc(order.rental.end_date)} ${esc(order.rental.return_time)}</dd></div><div><dt>수령·반납 상태</dt><dd>${order.fulfillment==='shipped'?'반납 완료':order.fulfillment==='processing'?'대여 중':'방문 수령 예정'}</dd></div>${order.rental.actual_pickup_at?`<div><dt>실제 수령 처리</dt><dd>${esc(new Date(order.rental.actual_pickup_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))}</dd></div>`:''}${order.rental.actual_return_at?`<div><dt>실제 반납 처리</dt><dd>${esc(new Date(order.rental.actual_return_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))}</dd></div>`:''}</dl>`:''}${calendarInfo(order,admin)}${admin&&customer&&!order.rental?`<details class="commerce-address"><summary>배송 정보 확인</summary><p>${esc(customer.name)} · ${esc(customer.phone)}<br>(${esc(customer.postcode)}) ${esc(customer.address)} ${esc(customer.address_detail)}</p></details>`:''}${admin&&customer?.evidence?.kind==='tax_invoice'?`<details class="commerce-address"><summary>세금계산서 요청 정보</summary><p>${esc(customer.evidence.corp_name)} · ${esc(customer.evidence.corp_num)}<br>대표 ${esc(customer.evidence.ceo_name)}<br>${esc(customer.evidence.address)}<br>${esc(customer.evidence.biz_type)} / ${esc(customer.evidence.biz_class)}<br>수신 ${esc(customer.evidence.email)}</p></details>`:''}${!admin?customerShipments(order):''}${documentCard(order.document)}<div class="commerce-actions">${admin?adminActions(order):customerActions(order)}</div><p class="commerce-feedback" role="status" hidden></p></article>`;
}
function customerActions(order){
 if(['APPROVED','PAYMENT_PENDING'].includes(order.state)&&!checkoutPaymentOpen)return '<p>일정과 요금이 확인되었습니다. 온라인 결제 연결을 준비 중입니다.</p>';
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
 let html='<section class="commerce-fulfillment"><h3>출고 · 반품 · 교환</h3>';
 if(eligible&&remaining.length)html+=`<form class="commerce-shipping" data-shipment-create><h4>${shipments.length?'남은 상품 출고':'상품 출고'}</h4><p>이번에 보낼 수량을 입력하세요. 0개인 품목은 다음 출고에 남습니다.</p><div class="commerce-quantities">${quantityFields(remaining)}</div>${shipmentTransport()}<button class="button-primary">선택 수량 출고 처리</button></form>`;
 for(const shipment of shipments){
  const available=caseRemaining(order,shipment);
  html+=`<details class="commerce-shipment"><summary>${shipment.purpose==='exchange'?'교환 재출고':'상품 출고'} · ${esc(shipment.carrier)} ${esc(shipment.tracking)}</summary><ul>${shipment.items.map(line=>'<li>'+esc(line.name||line.id)+' · '+esc(line.option||'기본 구성')+' · '+line.quantity+'개</li>').join('')}</ul>${shipment.created_at?'<p>'+new Date(shipment.created_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})+'</p>':'<p>기존 주문의 출고 내역</p>'}${canManage?`<form data-shipment-update="${esc(shipment.id)}">${shipmentTransport(shipment)}<button class="button-outline">운송정보 수정</button></form>`:''}${canManage&&available.length?`<details class="commerce-case-open"><summary>이 출고의 반품·교환 접수</summary><form data-case-create="${esc(shipment.id)}"><label>접수 유형<select name="kind"><option value="return">반품</option><option value="exchange">교환</option></select></label><div class="commerce-quantities">${quantityFields(available,false)}</div><label>접수 사유<textarea name="reason" minlength="2" maxlength="500" rows="3" required></textarea></label><p>이 기록은 결제 취소·환불을 실행하지 않습니다. 환불 결과는 결제사에서 별도로 확인하세요.</p><button class="button-outline">선택 수량 접수</button></form></details>`:''}</details>`;
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
 const approve=['REQUESTED','APPROVED'].includes(order.state)?prices+`<label class="commerce-check"><input type="checkbox" data-stock><span>${rental?'이 요청의 수량·구성별 재고와 수령·반납 방문 일정을 확인했습니다.':'이 주문의 수량·옵션별 재고와 납기를 확인했습니다.'}</span></label><button type="button" class="button-primary" data-approve>${rental?'전체 기간 대여 요금 확정':'주문 금액 확정'}</button>`:'';
 const visits=rental&&order.state==='PAID'&&order.payment_mode==='live'?(order.fulfillment==='unfulfilled'?'<button type="button" class="button-primary" data-rental-pickup>방문 수령 완료 처리</button>':order.fulfillment==='processing'?'<button type="button" class="button-primary" data-rental-return>방문 반납 완료 처리</button>':'<p>반납 완료</p>'):'';
 const ship=!rental?adminShipping(order):'';
 const reconcile=['CONFIRMING','PAYMENT_REVIEW','PAID','CANCELED'].includes(order.state)?'<button type="button" class="button-outline" data-reconcile>결제사 상태 다시 확인</button>':'';
 const receipt=order.document&&['retry','review','queued'].includes(order.document.status)?'<button type="button" class="button-outline" data-document-retry>증빙 상태 확인 · 재처리</button>':'';
 const cancel=['REQUESTED','APPROVED'].includes(order.state)?`<details class="commerce-cancel"><summary>미결제 접수 취소</summary><form data-cancel-request><p>결제를 시작하지 않은 주문의 접수를 취소합니다. 결제된 주문의 환불은 결제사에서 확인해야 합니다.</p><label>취소 사유<textarea name="reason" minlength="2" maxlength="500" rows="3" required></textarea></label><label class="commerce-check"><input type="checkbox" required><span>주문번호와 취소 사유를 확인했습니다.</span></label><button class="button-outline">접수 취소 확정</button></form></details>`:'';
 const locked=['PAYMENT_PENDING','CONFIRMING'].includes(order.state);
 const memo=`<form class="commerce-memo" data-admin-note><label>담당자 메모<textarea name="note" maxlength="2000" rows="3" placeholder="재고 확인 내용, 고객 요청과 다음 처리 내용을 기록하세요." ${locked?'disabled':''}>${esc(order.admin_note?.text||'')}</textarea></label><div><span>${locked?'결제 진행 중에는 메모를 변경할 수 없습니다.':order.admin_note?.updated_at?'마지막 저장 '+new Date(order.admin_note.updated_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'관리자에게만 보입니다.'}</span><button class="button-outline" ${locked?'disabled':''}>메모 저장</button></div></form>`;
 const canceled=order.admin_cancellation?`<p class="commerce-cancel-reason">접수 취소 사유: ${esc(order.admin_cancellation.reason)}</p>`:'';
 return approve+visits+ship+reconcile+receipt+cancel+canceled+memo;
}
let sdk;
function loadInicis(){return sdk||(sdk=new Promise((resolve,reject)=>{
 const script=document.createElement('script');script.src='https://paypro.inicis.com/std/payment/js/INIPayPro_v2.js';
 script.onload=()=>{if(window.INIPayPro?.requestPayment)resolve(window.INIPayPro);else{sdk=null;script.remove();reject(Error('이니시스 결제창을 불러오지 못했습니다.'));}};
 script.onerror=()=>{sdk=null;script.remove();reject(Error('결제창을 불러오지 못했습니다. 다시 시도해주세요.'));};document.head.append(script);
}).catch(error=>{sdk=null;throw error;}));}
function deviceType(){return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)||(/Macintosh/i.test(navigator.userAgent)&&navigator.maxTouchPoints>1)?'MOBILE':'WEB';}
function paymentForm(value){
 if(value.provider!=='inicis'||!['test','live'].includes(value.mode)||!Number.isSafeInteger(value.amount)||value.amount<1||value.amount>100000000||value.fields?.P_AMT!==String(value.amount)||value.fields?.P_OID!==value.orderId||value.fields?.P_NEXT_URL!==location.origin+'/api/inicis-return')throw Error('결제 요청 정보를 확인해주세요.');
 const form=document.createElement('form');form.id='inicis-payment-'+crypto.randomUUID();form.method='post';form.acceptCharset='UTF-8';form.hidden=true;
 for(const [name,fieldValue] of Object.entries(value.fields)){
  if(!/^P_[A-Z_]+$/.test(name)||typeof fieldValue!=='string')throw Error('결제 요청 형식을 확인해주세요.');
  const input=document.createElement('input');input.type='hidden';input.name=name;input.value=fieldValue;form.append(input);
 }
 return form;
}
async function paymentTest(){
 if(location.search)history.replaceState(null,'','/payment-test.html');
 const holder=main.querySelector('#payment-demo');
 let enabled=false;try{enabled=(await config()).ordersEnabled;}catch{}
 holder.innerHTML='<h2>KG이니시스</h2><p>'+(enabled?'확정된 주문의 결제 버튼을 누르면 이니시스 결제창으로 연결됩니다.':'온라인 결제 오픈을 준비하고 있습니다. 상품 구매와 견적은 상담으로 안내해드립니다.')+'</p><a class="button-primary" href="/checkout.html">주문서 확인 →</a>';
}
async function pay(order,card,button){
 if(button.disabled)return;
 const feedback=card.querySelector('.commerce-feedback');
 if(!card.querySelector('[data-quote-consent]').checked){message(feedback,'확정 금액을 확인하고 동의해주세요.');return;}
 button.disabled=true;message(feedback,'이니시스 결제창으로 연결하고 있습니다.');let form;
 try{
  const provider=await loadInicis();
  const value=await api('start',{id:order.id,quote_version:order.quote_version,device:deviceType()});
  form=paymentForm(value);document.body.append(form);
  provider.requestPayment(form,()=>{form.remove();button.disabled=false;message(feedback,'결제창을 닫았습니다. 주문 상태를 확인해주세요.');});
 }catch{form?.remove();message(feedback,'결제창 연결을 확인하지 못했습니다. 주문 상태를 확인한 뒤 다시 시도해주세요.');button.disabled=false;}
}
async function orders(){
 const container=main.querySelector('#commerce-content'),feedback=main.querySelector('#commerce-status');
 try{
  const ready=await config();checkoutPaymentOpen=ready.ordersEnabled===true;
  if(!ready.ordersEnabled&&!ready.rentalRequestsEnabled){container.innerHTML=blocked;return;}
  const params=new URLSearchParams(location.search);
  if(params.has('result'))history.replaceState(null,'','/orders.html'+location.hash);
  if(params.get('result')==='closed')message(feedback,'결제창을 닫았습니다. 아래 주문 상태를 확인해주세요.');
  else if(params.has('result'))message(feedback,'서버에 저장된 주문·결제 상태를 확인해주세요.');
  const {orders:list}=await api('orders');container.innerHTML=list.length?list.map(p=>orderCard(p)).join(''):'<div class="commerce-empty"><h2>접수한 주문이 없습니다.</h2><a href="/catalog.html">상품 둘러보기 →</a></div>';
  for(const order of list){const card=document.getElementById(order.id),button=card.querySelector('[data-pay]');if(button)button.onclick=()=>pay(order,card,button);}
  if(location.hash){const id=decodeURIComponent(location.hash.slice(1));document.getElementById(id)?.scrollIntoView({block:'start'});}
 }catch(error){message(feedback,error.message);container.innerHTML='';}
}
function adminReadiness(ready){
 const provider={inicis:'KG이니시스',toss:'토스페이먼츠'}[ready.paymentProvider]||'확인 필요';
 const rows=[['현재 결제대행사',provider],['고객 주문·결제',ready.ordersEnabled===true?'접수 가능':'오픈 준비 중'],['렌탈 온라인 접수',ready.rentalRequestsEnabled===true?'접수 가능':'오픈 준비 중'],['전자세금계산서',ready.taxInvoiceEnabled===true?'발급 연결됨':'발급 연결 준비 중']];
 return '<div class="commerce-admin-summary" aria-label="운영 연결 상태">'+rows.map(([label,value])=>'<div><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></div>').join('')+'</div><p class="commerce-note">현금영수증 소득공제·사업자 지출증빙은 결제대행사에서 처리합니다. 전자세금계산서는 별도 발급 연결이 필요합니다.</p>';
}
const adminTabs=[
 {id:'all',label:'전체 주문',count:'orders',filter:{}},
 {id:'requested',label:'재고·일정 확인',count:'requested',filter:{state:'REQUESTED'}},
 {id:'approved',label:'결제 대기',count:'approved',filter:{state:'APPROVED'}},
 {id:'shipping',label:'구매 출고',count:'toShip',filter:{queue:'purchase-shipping'}},
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
 if(order.state==='PAID')return order.fulfillment==='shipped'?'출고 완료':'출고·운송장 입력';
 return '주문 상세 확인';
}
function adminTable(orders,expandedId){
 if(!orders.length)return '<div class="commerce-empty commerce-admin-empty"><span>조회 결과 0건</span><h2>이 조건에 해당하는 주문이 없습니다.</h2><p>조회 기간이나 주문 상태를 바꿔 확인하세요. 새 주문이 접수되면 이곳에서 처리할 수 있습니다.</p></div>';
 return '<div class="commerce-table-wrap"><table class="commerce-table"><caption class="sr">주문 목록과 다음 처리</caption><thead><tr><th scope="col">주문</th><th scope="col">고객</th><th scope="col">상품·일정</th><th scope="col">금액</th><th scope="col">결제 상태</th><th scope="col">다음 처리</th><th scope="col">상세</th></tr></thead><tbody>'+orders.map(order=>{
  const rental=order.kind==='rental',open=expandedId===order.id;
  return `<tr class="commerce-order-row ${open?'is-expanded':''}"><td><span class="commerce-kind">${rental?'렌탈':'구매'}${order.payment_mode==='test'?' · 테스트':''}</span><strong>${esc(order.id)}</strong><time>${esc(new Date(order.created_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))}</time></td><td>${esc(order.customer?.name||'고객 정보 확인')}</td><td class="commerce-table-product"><strong>${esc(order.lines[0]?.name||'상품 확인')}${order.lines.length>1?' 외 '+(order.lines.length-1)+'종':''}</strong><span>${order.lines.reduce((n,p)=>n+p.quantity,0)}개${rental&&order.rental?' · '+esc(order.rental.start_date)+' → '+esc(order.rental.end_date):''}</span></td><td class="commerce-table-money">${money(order.total)}</td><td><span class="commerce-state" data-state="${esc(order.state)}">${esc(states[order.state]||'확인 필요')}</span></td><td>${esc(adminNext(order))}</td><td><button type="button" class="button-outline" data-open-order="${esc(order.id)}" aria-expanded="${open}" aria-controls="detail-${esc(order.id)}">${open?'닫기':'처리하기'}</button></td></tr><tr class="commerce-detail-row" ${open?'':'hidden'}><td colspan="7"><div id="detail-${esc(order.id)}">${orderCard(order,true).replace('</article>','<details class="commerce-history"><summary>처리 이력 확인</summary><div data-history></div></details></article>')}</div></td></tr>`;
 }).join('')+'</tbody></table></div>';
}
async function admin(){
 if(location.hostname==='order.nadaun.co')for(const link of document.querySelectorAll('a[href^="/"]')){const href=link.getAttribute('href');if(!href.startsWith('/#'))link.href='https://shop.nadaun.co'+href;}
 const container=main.querySelector('#commerce-content'),feedback=main.querySelector('#commerce-status');
 const year=new Date(Date.now()+9*3600000).getUTCFullYear();
 const reset={state:'',fulfillment:'',document:'',kind:'',queue:''};
 let filters={from:year+'-01-01',to:year+'-12-31',basis:'created',mode:'operational',...reset,search:'',page:1},busy=false,readiness,expandedId='',selectedTab='all';
 const options=(rows,selected)=>rows.map(([value,label])=>`<option value="${esc(value)}" ${selected===value?'selected':''}>${esc(label)}</option>`).join('');
 const params=()=>new URLSearchParams(Object.entries(filters).map(([k,v])=>[k,String(v)]));
 async function download(format,button){
  button.disabled=true;message(feedback,'전체 조회 결과를 파일로 준비하고 있습니다.');
  try{const query=params();query.set('action','admin-export');query.set('format',format);const response=await fetch('/api/orders?'+query,{credentials:'same-origin',cache:'no-store'});
   if(!response.ok){const value=await response.json();throw Error(value.error||'자료 다운로드를 확인해주세요.');}
   const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='nadaun-orders-'+filters.from+'_'+filters.to+'.'+format;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);message(feedback,'조회 조건에 해당하는 전체 자료를 다운로드했습니다.');
  }catch(error){message(feedback,error.message);}finally{button.disabled=false;}
 }
 const refresh=()=>list().catch(error=>{message(feedback,error.status===401?'로그인이 만료되었습니다. 새로고침 후 다시 로그인해주세요.':error.message);});
 async function list(){
  if(busy)return;busy=true;container.setAttribute('aria-busy','true');
  try{
   const response=await fetch('/api/orders?action=admin-orders&'+params(),{credentials:'same-origin',cache:'no-store'}),value=await response.json();
   if(!response.ok){const error=Error(value.error||'주문을 확인하지 못했습니다.');error.status=response.status;throw error;}
   let health=null;try{const response=await fetch('/api/orders?action=admin-calendar-health',{credentials:'same-origin',cache:'no-store'});if(response.ok)health=(await response.json()).calendar;}catch{}
   const s=value.summary,w=value.workload||s;
   const calendarStatus=health?.status==='connected'&&Date.now()-health.checked_at<180000?'캘린더 연결 확인':health?'캘린더 연결 점검 필요':'캘린더 연결 확인 중';
   const pg=readiness.paymentProvider==='inicis'?'<a href="https://iniweb.inicis.com/security/login.do" target="_blank" rel="noopener noreferrer">결제사 거래·환불 관리 ↗</a>':'';
   container.innerHTML=`<div class="commerce-admin-tools"><div><strong>주문 작업실</strong><span>마지막 조회 ${esc(new Date().toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul'}))}</span></div><button class="button-outline" data-refresh>새로고침</button><button class="button-outline" data-logout>로그아웃</button></div><nav class="commerce-work-tabs" aria-label="처리할 주문">${adminTabs.map(tab=>`<button type="button" data-worktab="${tab.id}" aria-pressed="${selectedTab===tab.id}"><span>${tab.label}</span>${Number.isFinite(w[tab.count])?'<strong>'+w[tab.count].toLocaleString('ko-KR')+'</strong>':''}</button>`).join('')}</nav><form class="commerce-admin-filter"><label>시작일<input type="date" name="from" value="${esc(filters.from)}" required></label><label>종료일<input type="date" name="to" value="${esc(filters.to)}" required></label><label>기간 기준<select name="basis">${options([['created','주문접수일'],['paid','결제확정일']],filters.basis)}</select></label><label>주문 유형<select name="kind">${options([['','구매·렌탈 전체'],['purchase','구매'],['rental','렌탈']],filters.kind)}</select></label><label>주문 상태<select name="state">${options([['','전체'],...Object.entries(states)],filters.state)}</select></label><label>배송·렌탈 처리<select name="fulfillment">${options([['','전체'],['unfulfilled','출고·수령 예정'],['processing','처리 중·대여 중'],['shipped','출고·반납 완료']],filters.fulfillment)}</select></label><label>결제 환경<select name="mode">${options([['operational','운영 주문 (테스트 제외)'],['live','실결제 주문'],['test','테스트 주문'],['all','전체']],filters.mode)}</select></label><label>증빙<select name="document">${options([['','전체'],['queued','발급 대기'],['processing','발급 확인 중'],['issued','발급 완료'],['retry','재확인 중'],['review','확인 필요'],['voided','취소'],['missing','미발급']],filters.document)}</select></label><label class="commerce-admin-search">주문번호 · 결제 거래번호<input type="search" name="search" value="${esc(filters.search)}" maxlength="80" placeholder="NS- 주문번호 또는 PG 거래번호"></label><div class="commerce-admin-filter-actions"><button class="button-primary">조회하기</button><button type="button" class="button-outline" data-days="7">최근 7일</button><button type="button" class="button-outline" data-days="30">최근 30일</button><button type="button" class="button-outline" data-year>올해 결제 자료</button><button type="button" class="button-outline" data-last-year>작년 결제 자료</button></div></form><div class="commerce-result-heading"><div><h2>조회 결과 <strong>${s.orders.toLocaleString('ko-KR')}</strong></h2><p>${esc(filters.from)} — ${esc(filters.to)} · ${selectedTab==='custom'?'상세 조건':adminTabs.find(t=>t.id===selectedTab)?.label||'전체 주문'}</p></div><div><button class="button-outline" data-export="xlsx">엑셀 다운로드</button><button class="button-outline" data-export="csv">CSV</button></div></div>${adminTable(value.orders,expandedId)}<nav class="commerce-admin-pages" aria-label="주문 페이지"><button class="button-outline" data-prev ${value.page<=1?'disabled':''}>← 이전</button><span>${value.page} / ${value.pages} 페이지 · 페이지당 ${value.pageSize}건</span><button class="button-outline" data-next ${value.page>=value.pages?'disabled':''}>다음 →</button></nav><details class="commerce-admin-connection"><summary>운영 연결 · 결제 · 자료 집계</summary>${adminReadiness(readiness)}<p class="commerce-calendar">${esc(calendarStatus)}</p><div class="commerce-admin-tools">${pg}<span>기프트는 수량·인쇄·납기 상담 후 진행합니다.</span></div><div class="commerce-admin-summary"><div><span>조회 주문의 실결제 원 승인 누계</span><strong>${money(s.approvedTotal)}</strong></div><div><span>취소 주문의 원 승인액</span><strong>${money(s.canceledOriginalTotal)}</strong></div><div><span>증빙 대기·확인</span><strong>${s.documentPending}건</strong></div></div><div class="commerce-admin-notes">${value.notices.map(n=>'<p>'+esc(n)+'</p>').join('')}</div></details>`;
   container.querySelector('[data-refresh]').onclick=refresh;
   container.querySelector('[data-logout]').onclick=async()=>{try{await api('logout',{});location.reload();}catch(error){message(feedback,error.message);}};
   const filterForm=container.querySelector('.commerce-admin-filter');
   filterForm.onsubmit=event=>{event.preventDefault();filters={...reset,...Object.fromEntries(new FormData(filterForm)),queue:'',page:1};selectedTab='custom';expandedId='';void refresh();};
   for(const button of container.querySelectorAll('[data-worktab]'))button.onclick=()=>{const tab=adminTabs.find(t=>t.id===button.dataset.worktab);filters={...filters,...reset,...tab.filter,page:1};selectedTab=tab.id;expandedId='';void refresh();};
   function annual(y){filters={from:y+'-01-01',to:y+'-12-31',basis:'paid',mode:'live',...reset,search:'',page:1};selectedTab='all';void refresh();}
   container.querySelector('[data-year]').onclick=()=>annual(year);container.querySelector('[data-last-year]').onclick=()=>annual(year-1);
   for(const button of container.querySelectorAll('[data-days]'))button.onclick=()=>{const today=Date.now()+9*3600000;filters={...filters,from:new Date(today-(Number(button.dataset.days)-1)*86400000).toISOString().slice(0,10),to:new Date(today).toISOString().slice(0,10),basis:'created',page:1};void refresh();};
   for(const button of container.querySelectorAll('[data-export]'))button.onclick=()=>download(button.dataset.export,button);
   container.querySelector('[data-prev]').onclick=()=>{filters.page--;void refresh();};container.querySelector('[data-next]').onclick=()=>{filters.page++;void refresh();};
   for(const button of container.querySelectorAll('[data-open-order]'))button.onclick=()=>{
    expandedId=expandedId===button.dataset.openOrder?'':button.dataset.openOrder;
    for(const other of container.querySelectorAll('[data-open-order]')){const open=other.dataset.openOrder===expandedId;other.setAttribute('aria-expanded',String(open));other.textContent=open?'닫기':'처리하기';const row=other.closest('tr');row.classList.toggle('is-expanded',open);row.nextElementSibling.hidden=!open;}
   };
   for(const order of value.orders){
    const card=document.getElementById(order.id),status=card.querySelector('.commerce-feedback');
    const history=card.querySelector('.commerce-history');history.ontoggle=async()=>{if(!history.open||history.dataset.loaded)return;const target=history.querySelector('[data-history]');try{const result=await fetch('/api/orders?action=admin-events&id='+encodeURIComponent(order.id),{credentials:'same-origin',cache:'no-store'}),data=await result.json();if(!result.ok)throw Error(data.error||'처리 이력을 확인하지 못했습니다.');const actions={order_requested:'주문 접수',admin_note_updated:'담당자 메모 저장',request_canceled:'미결제 접수 취소',admin_note_cleared:'담당자 메모 지움',rental_picked_up:'방문 수령 완료',rental_returned:'방문 반납 완료',quote_approved:'재고·납기 확인 / 금액 확정',payment_started:'결제 시작',payment_confirming:'결제 승인 요청',payment_done:'결제 승인 저장',payment_canceled:'전체 취소 확인',payment_partial_canceled:'부분 취소 확인',payment_net_canceled:'승인 복구 취소',payment_review:'결제 확인 필요',order_shipped:'전체 출고 완료',order_partially_shipped:'일부 상품 출고',order_tracking_updated:'운송정보 수정',return_case_created:'반품 접수',exchange_case_created:'교환 접수',case_approved:'반품·교환 승인',case_returning:'상품 회수 진행',case_received:'상품 회수 확인',case_closed:'반품·교환 기록 종결',case_rejected:'반품·교환 접수 거절',exchange_shipped:'교환품 재출고',document_payment_changed:'증빙 처리 중 결제 변경 확인'};target.innerHTML='<ol>'+data.events.map(e=>'<li><time>'+esc(new Date(e.created_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))+'</time> '+esc(actions[e.action]||e.action)+' <small>'+esc(e.actor)+'</small></li>').join('')+'</ol>';history.dataset.loaded='true';}catch(error){target.textContent=error.message;}};
    async function change(action,body,button){button.disabled=true;try{await api(action,{id:order.id,version:order.version,...body});await list();message(feedback,'주문 '+order.id+' 처리 내용을 저장했습니다.');}catch(error){message(status,error.message);button.disabled=false;}}
    const approve=card.querySelector('[data-approve]');if(approve)approve.onclick=()=>{const prices=[...card.querySelectorAll('[data-rental-price]')];if(prices.some(input=>!input.reportValidity()))return;change('admin-approve',{stock_confirmed:card.querySelector('[data-stock]').checked,...(order.kind==='rental'?{rental_prices:order.lines.map((line,i)=>({id:line.id,option:line.option,unit_price:Number(prices[i].value)}))}:{})},approve);};
    for(const [selector,action] of [['[data-rental-pickup]','admin-rental-pickup'],['[data-rental-return]','admin-rental-return'],['[data-reconcile]','admin-reconcile'],['[data-document-retry]','admin-document-retry']]){const button=card.querySelector(selector);if(button)button.onclick=()=>change(action,{},button);}
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
 try{readiness=await config();checkoutPaymentOpen=readiness.ordersEnabled===true;if(!readiness.adminEnabled){container.innerHTML='<div class="commerce-empty"><h2>주문 관리 연결 준비 중</h2><p>주문 저장소와 관리자 인증 설정을 확인해주세요.</p></div>';return;}await list();}
 catch(error){
  if(error.status!==401){message(feedback,error.message);return;}
  container.innerHTML='<div class="commerce-login-layout"><div class="commerce-login-intro"><span class="section-index">NADAUN SPACE / OPERATIONS</span><h2>주문이 들어오면,<br>여기서 이어갑니다.</h2><p>구매의 재고 확인과 출고,<br>렌탈의 수령과 반납을 한곳에서 관리합니다.</p></div><form class="commerce-login"><h2>관리자 로그인</h2>'+(readiness.adminLoginRequiresEmail?'<label>관리자 이메일<input type="email" name="email" autocomplete="username" maxlength="254" required></label>':'')+'<label>관리자 비밀번호<input type="password" name="password" autocomplete="current-password" minlength="16" maxlength="128" required></label><button class="button-primary">로그인 →</button><p class="commerce-note">승인된 관리자만 주문과 고객 정보를 확인할 수 있습니다.</p></form></div>';
  const form=container.querySelector('form');form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('button');button.disabled=true;try{await api('login',Object.fromEntries(new FormData(form)));form.reset();message(feedback,'');await list();}catch(error){message(feedback,error.message);button.disabled=false;}};
 }
}
if(mode==='checkout'){document.addEventListener('shop:content-updated',mountCheckout);void mountCheckout();}
else if(mode==='orders')void orders();else if(mode==='admin')void admin();else if(mode==='payment-test')void paymentTest();
