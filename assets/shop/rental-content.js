(function(root){
 'use strict';
 const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const won=value=>Number(value).toLocaleString('ko-KR');
 const imageUrl=value=>/^https:\/\//.test(value||'')||/^\/assets\//.test(value||'')?esc(value):'';
 function price(product){
  const value=product.rental?.price??product.sale_price??product.price;
  const period=product.rental?.period;
  return {value,label:period?period+' 기준':product.rental?.service==='studio'?'이용시간 확인':'대여기간 확인'};
 }
 function priceHTML(product){const p=price(product);return `${p.value==null?'요금 상담':won(p.value)+'<small>원</small>'}<span class="rental-period-label">${esc(p.label)}</span>`;}
 function requestForm(product,rental,studio){
  const rates=rental.rates||[];
  return `<form class="rental-request-form" data-rental-request data-product-id="${esc(product.id)}"><h2>${studio?'이용 일정':'대여 일정'} 선택</h2><div class="rental-schedule-fields"><label>대여 시작일 (월/일)<input type="date" name="start_date" required></label><label>대여 종료일 (월/일)<input type="date" name="end_date" required></label><label>${studio?'입실':'수령'} 방문 시간<input type="time" name="pickup_time" step="60" required></label><label>${studio?'퇴실':'반납'} 방문 시간<input type="time" name="return_time" step="60" required></label></div><label>수량<input type="number" name="quantity" min="1" max="99" step="1" value="1" inputmode="numeric" required></label>${rates.length?`<label>희망 요금 구성<select name="option" aria-label="희망 요금 구성"><option value="">방문 일정에 맞춰 요금 확인 요청</option>${rates.map(rate=>`<option value="${esc(rate.label)}">${esc(rate.label)} · ${won(rate.price)}원</option>`).join('')}</select></label>`:'<input type="hidden" name="option" value="">'}<p class="rental-schedule-preview" data-rental-preview role="status">시작·종료 날짜와 방문 시간을 정확히 선택해주세요.</p><button type="button" class="button-outline" data-rental-save>선택 일정 저장</button><div class="rental-customer-fields" data-rental-customer hidden><label>예약자 이름<input name="name" type="text" minlength="2" maxlength="60" autocomplete="name" disabled required></label><label>연락처<input name="phone" type="tel" maxlength="20" autocomplete="tel" disabled required></label><label>결제·증빙 선택<select name="evidence_kind" aria-label="결제·증빙 선택" disabled><option value="card_receipt">카드 결제 · 카드 매출전표</option><option value="cash_receipt">계좌이체 · 현금영수증 / 지출증빙</option></select></label><div data-rental-tax hidden></div><p>현금영수증 용도와 발급 정보는 이니시스 결제창에서 선택합니다. 전자세금계산서는 발급 연결 후 선택할 수 있습니다.</p><label class="rental-consent"><input type="checkbox" name="consent" disabled required><span>렌탈 일정·요금 확인과 선택한 증빙 처리를 위한 이름·연락처·방문 일정 및 입력한 사업자 정보 수집·이용에 동의합니다. <a href="/privacy.html" target="_blank" rel="noopener">개인정보 처리 안내</a></span></label></div><button type="submit" class="button-primary" data-rental-submit disabled>온라인 렌탈 접수 준비 중</button><p class="rental-request-feedback" data-rental-feedback role="status" hidden></p><p class="rental-note">일정 저장은 예약 확정이 아닙니다. 재고와 방문 일정을 확인한 후 전체 대여 기간의 요금을 안내해드립니다.</p></form>`;
 }
 async function mountRequest(form){
  if(!form||form.dataset.mounted)return;form.dataset.mounted='true';
  const field=name=>form.querySelector('[name="'+name+'"]'),feedback=form.querySelector('[data-rental-feedback]'),submit=form.querySelector('[data-rental-submit]'),preview=form.querySelector('[data-rental-preview]'),key='nadaun-rental-draft-v1:'+form.dataset.productId;
  const today=new Date(Date.now()+9*3600000).toISOString().slice(0,10),scheduleNames=['start_date','end_date','pickup_time','return_time'];
  field('start_date').min=today;field('end_date').min=today;
  const message=text=>{feedback.textContent=text;feedback.hidden=!text;};
  function update(){field('end_date').min=field('start_date').value||today;const start=Date.parse(field('start_date').value+'T'+field('pickup_time').value+':00+09:00'),end=Date.parse(field('end_date').value+'T'+field('return_time').value+':00+09:00');field('return_time').setCustomValidity(Number.isFinite(start)&&Number.isFinite(end)&&end<=start?'반납 일시는 수령 일시보다 늦어야 합니다.':'');preview.textContent=Number.isFinite(start)&&Number.isFinite(end)?field('start_date').value+' '+field('pickup_time').value+' 수령 → '+field('end_date').value+' '+field('return_time').value+' 반납':'시작·종료 날짜와 방문 시간을 정확히 선택해주세요.';}
  try{const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved){for(const name of [...scheduleNames,'quantity','option'])if(typeof saved[name]==='string')field(name).value=saved[name];}}catch{}
  for(const name of scheduleNames)field(name).addEventListener('change',update);update();
  function draft(){update();for(const name of [...scheduleNames,'quantity'])if(!field(name).reportValidity())return null;return Object.fromEntries([...scheduleNames,'quantity','option'].map(name=>[name,field(name).value]));}
  form.querySelector('[data-rental-save]').onclick=()=>{const value=draft();if(!value)return;try{localStorage.setItem(key,JSON.stringify(value));message('선택한 일정을 이 브라우저에 저장했습니다. '+preview.textContent);}catch{message('일정을 저장하지 못했습니다. 브라우저 저장 설정을 확인해주세요.');}};
  async function api(action,body,headers={}){const response=await fetch('/api/orders?action='+encodeURIComponent(action),{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:{...(body===undefined?{}:{'Content-Type':'application/json'}),...headers},...(body===undefined?{}:{body:JSON.stringify(body)})});const value=await response.json();if(!response.ok){const error=Error(value.error||'렌탈 접수를 확인하지 못했습니다.');error.status=response.status;throw error;}return value;}
  let ready;try{ready=await api('config');}catch{return;}if(!form.isConnected||!ready.rentalRequestsEnabled)return;
  const customer=form.querySelector('[data-rental-customer]');customer.hidden=false;customer.querySelectorAll('input,select').forEach(input=>input.disabled=false);
  const evidence=field('evidence_kind'),tax=form.querySelector('[data-rental-tax]');
  if(ready.taxInvoiceEnabled){const option=document.createElement('option');option.value='tax_invoice';option.textContent='계좌이체 · 전자세금계산서';evidence.append(option);tax.innerHTML=[['corp_num','사업자등록번호 (숫자 10자리)','text',10],['corp_name','상호','text',200],['ceo_name','대표자명','text',100],['address','사업장 주소','text',300],['biz_type','업태','text',100],['biz_class','종목','text',100],['email','세금계산서 수신 이메일','email',100]].map(([name,label,type,max])=>`<label>${label}<input name="tax_${name}" type="${type}" maxlength="${max}" disabled ${name==='corp_num'?'inputmode="numeric" pattern="[0-9]{10}"':''}></label>`).join('');}
  evidence.onchange=()=>{const active=evidence.value==='tax_invoice';tax.hidden=!active;tax.querySelectorAll('input').forEach(input=>{input.disabled=!active;input.required=active;});};evidence.onchange();submit.disabled=false;submit.textContent='렌탈 일정 접수하기';
  const requestKey=crypto.randomUUID();let payload;
  form.addEventListener('submit',async event=>{event.preventDefault();if(submit.disabled)return;submit.disabled=true;message('렌탈 일정을 접수하고 있습니다.');try{if(!payload){const value=draft();if(!value||!form.reportValidity()){submit.disabled=false;return;}payload={customer:{name:field('name').value,phone:field('phone').value,consent:field('consent').checked},rental:Object.fromEntries(scheduleNames.map(name=>[name,value[name]])),items:[{id:form.dataset.productId,option:value.option,quantity:Number(value.quantity)}],evidence:{kind:evidence.value}};if(evidence.value==='tax_invoice')for(const name of ['corp_num','corp_name','ceo_name','address','biz_type','biz_class','email'])payload.evidence[name]=field('tax_'+name).value;}
   form.querySelectorAll('input,select').forEach(input=>input.disabled=true);await api('session',{});const value=await api('rental-create',payload,{'Idempotency-Key':requestKey});location.assign('/orders.html#'+encodeURIComponent(value.order.id));
  }catch(error){message(error.message+(error.status&&error.status<500?'':' 입력한 내용 그대로 다시 접수 버튼을 눌러주세요.'));if(error.status&&error.status<500&&error.status!==429){payload=undefined;form.querySelectorAll('input,select').forEach(input=>input.disabled=false);evidence.onchange();}submit.disabled=false;}});
 }
 function render(product,detail,{brand='' }={}){
  const rental=detail.rental||{rates:[],components:[],notes:[],packing_confirmation_required:true,period_confirmation_required:true};
  const studio=product.rental?.service==='studio';
  const supplied=detail.images?.main||[];
  const gallery=[...new Set([supplied[0]||product.image,...supplied.slice(1)])].filter(u=>imageUrl(u));
  const brandUrl='/brands/'+encodeURIComponent(product.brand_id)+'.html?kind=rental';
  const tags=(product.discovery?.tags||[]).map(tag=>`<a href="/catalog.html?kind=rental&amp;q=${encodeURIComponent(tag)}">#${esc(tag.replace(/\s+/g,''))}</a>`).join('');
  const rates=rental.rates.length?`<dl class="rental-rates">${rental.rates.map(rate=>`<div><dt>${esc(rate.label)}</dt><dd>${won(rate.price)}<small>원</small></dd></div>`).join('')}</dl>`:'<p class="rental-note">표시 요금의 적용 기간은 예약 전 상담으로 확인해주세요.</p>';
  const packing=rental.components.length?`<ul class="rental-components">${rental.components.map(item=>`<li><span>${esc(item.name)}</span><strong>${esc(item.quantity)}개</strong></li>`).join('')}</ul>`:'';
  const notes=rental.notes.length?`<div class="rental-source-notes">${rental.notes.map(note=>`<p>${esc(note)}</p>`).join('')}</div>`:'';
  const details=(detail.images?.detail||[]).filter(u=>imageUrl(u));
  return `<div class="rental-product"><div class="breadcrumb"><a href="/">홈</a><span>›</span><a href="/catalog.html?kind=rental">제품 렌탈</a><span>›</span><a href="${brandUrl}">${esc(brand)}</a></div><section class="detail-layout"><div class="rental-gallery"><div class="gallery-main"><img id="gallery-image" data-rental-fallback="${imageUrl(product.image)}" src="${imageUrl(gallery[0])}" alt="${esc(product.name)}" referrerpolicy="no-referrer"></div>${gallery.length>1?`<div class="gallery-thumbs" aria-label="렌탈 상품 이미지">${gallery.map((url,i)=>`<button type="button" data-rental-image="${imageUrl(url)}" class="${i===0?'active':''}" aria-label="상품 이미지 ${i+1}" aria-pressed="${i===0}"><img src="${imageUrl(url)}" alt="" loading="lazy" referrerpolicy="no-referrer"></button>`).join('')}</div>`:''}</div><div class="detail-info"><a class="detail-brand" href="${brandUrl}">${esc(brand)} ↗</a><p class="rental-kind">${studio?'STUDIO RENTAL · 스튜디오 대여':'EQUIPMENT RENTAL · 장비 대여'}</p><h1>${esc(product.name)}</h1><div class="detail-price">${priceHTML(product)}</div><section class="rental-rate-section" aria-label="대여 기간별 요금"><h2>${studio?'이용 요금':'대여 요금'}</h2>${rates}<p class="rental-note">예약 가능 여부와 ${studio?'사용 인원·시간':'장비 구성·픽업 및 반납 시간'}을 확인한 후 예약을 확정합니다.</p></section>${requestForm(product,rental,studio)}<div class="rental-contact"><a class="button-primary" href="https://talk.naver.com/ct/w4w1o8" target="_blank" rel="noopener">네이버 톡톡 · 일정 상담</a><a class="button-outline" href="https://pf.kakao.com/_pyNxnxb/chat" target="_blank" rel="noopener">카카오톡 · 일정 상담</a></div><p class="rental-note">상담 시 상품명, 수량, ${studio?'사용 시간':'픽업·반납 일시'}를 알려주세요.</p><p class="rental-item-number">상품번호 ${esc(product.id)}</p><nav class="product-tags" aria-label="관련 상품 검색">${tags}</nav></div></section><nav class="detail-tabs" aria-label="렌탈 상세 안내"><a href="#rental-components">${studio?'공간 안내':'포함 구성품'}</a>${details.length?'<a href="#rental-specifications">상세 사진·사양</a>':''}<a href="#rental-use">${studio?'스튜디오 이용':'픽업·반납'} 안내</a></nav><section class="description rental-contents" id="rental-components"><h2>${studio?'공간 안내':'포함 구성품'}</h2>${packing}${rental.packing_confirmation_required?'<p class="rental-note">포함 장비와 구성품은 예약 전에 확인해주세요.</p>':''}${notes}</section>${details.length?`<section class="description" id="rental-specifications"><h2>상세 사진·사양</h2><p class="rental-note">대여 구성은 위의 포함 구성품을 기준으로 확인해주세요.</p>${details.map((url,i)=>`<img src="${imageUrl(url)}" alt="${esc(product.name)} 상세 정보 ${i+1}" loading="lazy" decoding="async" referrerpolicy="no-referrer">`).join('')}</section>`:''}<section class="description rental-use" id="rental-use"><h2>${studio?'스튜디오 이용 안내':'픽업·반납 안내'}</h2>${studio?'<p>원하시는 사용 날짜·시간과 인원을 알려주세요. 공간 이용 조건과 예약 가능 시간을 확인해드립니다.</p><a class="button-outline" href="/studio.html">스튜디오 자세히 보기 ↗</a>':'<ol><li><strong>장비와 일정 확인</strong><p>장비명·수량·픽업 및 반납 일시를 알려주세요.</p></li><li><strong>요금과 구성 확인</strong><p>대여 기간별 요금과 필요한 옵션, 포함 구성품을 확인합니다.</p></li><li><strong>예약 확정 후 픽업·반납</strong><p>확정된 시간에 장비를 수령하고 약정한 일정에 반납해주세요.</p></li></ol><p>픽업 장소 · 서울 영등포구 영등포로33길 18, 1층 나다운 스페이스</p>'}<p>문의 <a href="tel:0507-1394-6231">0507-1394-6231</a></p></section></div>`;
 }
 function mount(container){
  const form=container.querySelector('[data-rental-request]');if(form)mountRequest(form);
  const image=container.querySelector('#gallery-image');
  if(image){
   const fallback=()=>{
    const url=image.dataset.rentalFallback;
    if(!url||!imageUrl(url)||image.getAttribute('src')===url)return;
    image.src=url;
   };
   image.addEventListener('error',fallback);
   if(image.complete&&image.naturalWidth===0)fallback();
  }
  for(const button of container.querySelectorAll('[data-rental-image]'))button.addEventListener('click',()=>{
   const gallery=container.querySelector('#gallery-image');if(!gallery)return;
   gallery.src=button.dataset.rentalImage;
   for(const item of container.querySelectorAll('[data-rental-image]')){item.classList.toggle('active',item===button);item.setAttribute('aria-pressed',String(item===button));}
  });
 }
 const api={price,priceHTML,render,mount,requestForm};
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.NadaunRental=api;
})(typeof globalThis!=='undefined'?globalThis:this);
