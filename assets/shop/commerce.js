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
const config=()=>configRequest||(configRequest=api('config'));
function message(target,text){target.textContent=text;target.hidden=!text;}
const notice='<p class="commerce-note">이 브라우저에서 접수한 주문을 확인할 수 있습니다. 다른 기기에서 확인하거나 브라우저 데이터를 삭제한 경우에는 주문번호로 고객센터에 문의해주세요.</p>';
const blocked='<div class="commerce-empty"><h2>온라인 주문 오픈 준비 중입니다.</h2><p>상품 구매와 견적은 상담으로 안내해드립니다.</p><a class="button-primary" href="https://pf.kakao.com/_pyNxnxb/chat" target="_blank" rel="noopener">카카오톡 구매 상담 ↗</a></div>';
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
   if(!sentPayload){const fields=new FormData(form),items=JSON.parse(localStorage.getItem('nadaun-shop-cart-v1')||'[]');sentPayload={customer:Object.fromEntries(['name','phone','postcode','address','address_detail'].map(k=>[k,fields.get(k)])),items};sentPayload.customer.consent=fields.has('consent');sentPayload.evidence={kind:fields.get('evidence_kind')};if(sentPayload.evidence.kind==='tax_invoice')for(const k of ['corp_num','corp_name','ceo_name','address','biz_type','biz_class','email'])sentPayload.evidence[k]=fields.get('tax_'+k);}
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
function orderCard(order,admin=false){
 const customer=order.customer;
 return `<article class="commerce-order" id="${esc(order.id)}"><header><div><span class="section-index">${esc(order.id)}</span><h2>${order.payment_mode==='test'?'테스트 · ':''}${esc(states[order.state]||'상태 확인 필요')}</h2></div><time>${esc(new Date(order.created_at).toLocaleString('ko-KR'))}</time></header><ul class="commerce-lines">${order.lines.map(p=>`<li><a href="/item.html?id=${encodeURIComponent(p.id)}">${esc(p.name)}<small>${esc(p.option||'기본 구성')} · ${p.quantity}개</small></a><strong>${money(p.unit_price===null?null:p.unit_price*p.quantity)}</strong></li>`).join('')}</ul><div class="commerce-totals"><span>상품 ${money(order.subtotal)} + 배송 ${money(order.shipping)}</span><strong>${money(order.total)}</strong></div>${order.fulfillment==='shipped'?`<p class="commerce-shipped">출고 완료 · ${esc(order.carrier)} ${esc(order.tracking)}</p>`:''}${admin&&customer?`<details class="commerce-address"><summary>배송 정보 확인</summary><p>${esc(customer.name)} · ${esc(customer.phone)}<br>(${esc(customer.postcode)}) ${esc(customer.address)} ${esc(customer.address_detail)}</p></details>`:''}${documentCard(order.document)}<div class="commerce-actions">${admin?adminActions(order):customerActions(order)}</div><p class="commerce-feedback" role="status" hidden></p></article>`;
}
function customerActions(order){
 if(['APPROVED','PAYMENT_PENDING'].includes(order.state))return `<p>결제 가능 시간: ${esc(new Date(order.quote_expires).toLocaleString('ko-KR'))}까지</p><label class="commerce-check"><input type="checkbox" data-quote-consent><span>상품 구성과 배송비를 포함한 확정 금액 ${money(order.total)}을 확인했습니다.</span></label><button type="button" class="button-primary" data-pay="${esc(order.id)}">${money(order.total)} 결제하기 →</button>`;
 if(order.state==='REQUESTED')return '<p>재고·납기 확인 후 결제가 열립니다.</p>';
 if(['CONFIRMING','PAYMENT_REVIEW'].includes(order.state))return '<p>결제 결과를 확인하고 있습니다. 중복 결제하지 말고 고객센터에 주문번호를 알려주세요.</p>';
 return '';
}
function adminActions(order){
 const approve=['REQUESTED','APPROVED'].includes(order.state)?'<label class="commerce-check"><input type="checkbox" data-stock><span>이 주문의 수량·옵션별 재고와 납기를 확인했습니다.</span></label><button type="button" class="button-primary" data-approve>금액 확정 · 결제 허용</button>':'';
 const ship=order.state==='PAID'&&order.payment_mode==='live'?`<form class="commerce-shipping"><label>택배사<input name="carrier" value="${esc(order.carrier)}" maxlength="40" required></label><label>운송장 번호<input name="tracking" value="${esc(order.tracking)}" maxlength="30" pattern="[0-9][0-9-]{5,29}" required></label><button class="button-primary">${order.fulfillment==='shipped'?'운송장 수정':'출고 처리'}</button></form>`:'';
 const reconcile=['CONFIRMING','PAYMENT_REVIEW','PAID','CANCELED'].includes(order.state)?'<button type="button" class="button-outline" data-reconcile>결제사 상태 다시 확인</button>':'';
 const receipt=order.document&&['retry','review','queued'].includes(order.document.status)?'<button type="button" class="button-outline" data-document-retry>증빙 상태 확인 · 재처리</button>':'';
 return approve+ship+reconcile+receipt;
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
  if(!(await config()).ordersEnabled){container.innerHTML=blocked;return;}
  const params=new URLSearchParams(location.search);
  if(params.has('result'))history.replaceState(null,'','/orders.html'+location.hash);
  if(params.get('result')==='closed')message(feedback,'결제창을 닫았습니다. 아래 주문 상태를 확인해주세요.');
  else if(params.has('result'))message(feedback,'서버에 저장된 주문·결제 상태를 확인해주세요.');
  const {orders:list}=await api('orders');container.innerHTML=list.length?list.map(p=>orderCard(p)).join(''):'<div class="commerce-empty"><h2>접수한 주문이 없습니다.</h2><a href="/catalog.html">상품 둘러보기 →</a></div>';
  for(const order of list){const card=document.getElementById(order.id),button=card.querySelector('[data-pay]');if(button)button.onclick=()=>pay(order,card,button);}
  if(location.hash){const id=decodeURIComponent(location.hash.slice(1));document.getElementById(id)?.scrollIntoView({block:'start'});}
 }catch(error){message(feedback,error.message);container.innerHTML='';}
}
async function admin(){
 const container=main.querySelector('#commerce-content'),feedback=main.querySelector('#commerce-status');
 async function list(){
  const value=await api('admin-orders');container.innerHTML='<div class="commerce-admin-tools"><span>최근 주문 '+value.orders.length+'건</span><button class="button-outline" data-refresh>새로고침</button><button class="button-outline" data-logout>로그아웃</button></div>'+value.orders.map(p=>orderCard(p,true)).join('')+(value.orders.length?'':'<p class="commerce-empty">접수된 주문이 없습니다.</p>');
  container.querySelector('[data-refresh]').onclick=()=>list().catch(error=>message(feedback,error.message));
  container.querySelector('[data-logout]').onclick=async()=>{try{await api('logout',{});location.reload();}catch(error){message(feedback,error.message);}};
  for(const order of value.orders){
   const card=document.getElementById(order.id),status=card.querySelector('.commerce-feedback');
   async function change(action,body,button){button.disabled=true;try{await api(action,{id:order.id,version:order.version,...body});await list();}catch(error){message(status,error.message);button.disabled=false;}}
   const approve=card.querySelector('[data-approve]');if(approve)approve.onclick=()=>change('admin-approve',{stock_confirmed:card.querySelector('[data-stock]').checked},approve);
   const reconcile=card.querySelector('[data-reconcile]');if(reconcile)reconcile.onclick=()=>change('admin-reconcile',{},reconcile);
   const receipt=card.querySelector('[data-document-retry]');if(receipt)receipt.onclick=()=>change('admin-document-retry',{},receipt);
   const ship=card.querySelector('.commerce-shipping');if(ship)ship.onsubmit=event=>{event.preventDefault();change('admin-ship',Object.fromEntries(new FormData(ship)),ship.querySelector('button'));};
  }
 }
 try{if(!(await config()).ordersEnabled){container.innerHTML='<div class="commerce-empty"><h2>주문 관리 연결 준비 중</h2><p>주문 저장소와 관리자 인증 설정을 완료한 뒤 이용할 수 있습니다.</p></div>';return;}await list();}
 catch(error){
  if(error.status!==401){message(feedback,error.message);return;}
  container.innerHTML='<form class="commerce-login"><label>관리자 비밀번호<input type="password" name="password" autocomplete="current-password" minlength="16" maxlength="128" required></label><button class="button-primary">로그인 →</button></form>';
  const form=container.querySelector('form');form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('button');button.disabled=true;try{await api('login',{password:new FormData(form).get('password')});form.reset();message(feedback,'');await list();}catch(error){message(feedback,error.message);button.disabled=false;}};
 }
}
if(mode==='checkout'){document.addEventListener('shop:content-updated',mountCheckout);void mountCheckout();}
else if(mode==='orders')void orders();else if(mode==='admin')void admin();else if(mode==='payment-test')void paymentTest();
