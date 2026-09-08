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
  return `<div class="rental-product"><div class="breadcrumb"><a href="/">홈</a><span>›</span><a href="/catalog.html?kind=rental">제품 렌탈</a><span>›</span><a href="${brandUrl}">${esc(brand)}</a></div><section class="detail-layout"><div class="rental-gallery"><div class="gallery-main"><img id="gallery-image" data-rental-fallback="${imageUrl(product.image)}" src="${imageUrl(gallery[0])}" alt="${esc(product.name)}" referrerpolicy="no-referrer"></div>${gallery.length>1?`<div class="gallery-thumbs" aria-label="렌탈 상품 이미지">${gallery.map((url,i)=>`<button type="button" data-rental-image="${imageUrl(url)}" class="${i===0?'active':''}" aria-label="상품 이미지 ${i+1}" aria-pressed="${i===0}"><img src="${imageUrl(url)}" alt="" loading="lazy" referrerpolicy="no-referrer"></button>`).join('')}</div>`:''}</div><div class="detail-info"><a class="detail-brand" href="${brandUrl}">${esc(brand)} ↗</a><p class="rental-kind">${studio?'STUDIO RENTAL · 스튜디오 대여':'EQUIPMENT RENTAL · 장비 대여'}</p><h1>${esc(product.name)}</h1><div class="detail-price">${priceHTML(product)}</div><section class="rental-rate-section" aria-label="대여 기간별 요금"><h2>${studio?'이용 요금':'대여 요금'}</h2>${rates}<p class="rental-note">예약 가능 여부와 ${studio?'사용 인원·시간':'장비 구성·픽업 및 반납 시간'}을 확인한 후 예약을 확정합니다.</p></section><div class="rental-contact"><a class="button-primary" href="https://talk.naver.com/ct/w4w1o8" target="_blank" rel="noopener">네이버 톡톡 · 일정 상담</a><a class="button-outline" href="https://pf.kakao.com/_pyNxnxb/chat" target="_blank" rel="noopener">카카오톡 · 일정 상담</a></div><p class="rental-note">상담 시 상품명, 수량, ${studio?'사용 시간':'픽업·반납 일시'}를 알려주세요.</p><p class="rental-item-number">상품번호 ${esc(product.id)}</p><nav class="product-tags" aria-label="관련 상품 검색">${tags}</nav></div></section><nav class="detail-tabs" aria-label="렌탈 상세 안내"><a href="#rental-components">${studio?'공간 안내':'포함 구성품'}</a>${details.length?'<a href="#rental-specifications">상세 사진·사양</a>':''}<a href="#rental-use">${studio?'스튜디오 이용':'픽업·반납'} 안내</a></nav><section class="description rental-contents" id="rental-components"><h2>${studio?'공간 안내':'포함 구성품'}</h2>${packing}${rental.packing_confirmation_required?'<p class="rental-note">포함 장비와 구성품은 예약 전에 확인해주세요.</p>':''}${notes}</section>${details.length?`<section class="description" id="rental-specifications"><h2>상세 사진·사양</h2><p class="rental-note">대여 구성은 위의 포함 구성품을 기준으로 확인해주세요.</p>${details.map((url,i)=>`<img src="${imageUrl(url)}" alt="${esc(product.name)} 상세 정보 ${i+1}" loading="lazy" decoding="async" referrerpolicy="no-referrer">`).join('')}</section>`:''}<section class="description rental-use" id="rental-use"><h2>${studio?'스튜디오 이용 안내':'픽업·반납 안내'}</h2>${studio?'<p>원하시는 사용 날짜·시간과 인원을 알려주세요. 공간 이용 조건과 예약 가능 시간을 확인해드립니다.</p><a class="button-outline" href="/studio.html">스튜디오 자세히 보기 ↗</a>':'<ol><li><strong>장비와 일정 확인</strong><p>장비명·수량·픽업 및 반납 일시를 알려주세요.</p></li><li><strong>요금과 구성 확인</strong><p>대여 기간별 요금과 필요한 옵션, 포함 구성품을 확인합니다.</p></li><li><strong>예약 확정 후 픽업·반납</strong><p>확정된 시간에 장비를 수령하고 약정한 일정에 반납해주세요.</p></li></ol><p>픽업 장소 · 서울 영등포구 영등포로33길 18, 1층 나다운 스페이스</p>'}<p>문의 <a href="tel:0507-1394-6231">0507-1394-6231</a></p></section></div>`;
 }
 function mount(container){
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
 const api={price,priceHTML,render,mount};
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.NadaunRental=api;
})(typeof globalThis!=='undefined'?globalThis:this);
