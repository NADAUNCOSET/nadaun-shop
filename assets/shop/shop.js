import {isDiscounted,isPromotion,matchesBenefit,benefitNavigation,categoryTrail,categoryControls,catalogSelection,productTypeNavigation,brandSelectionHref} from './catalog-tools.js';
import {mountPurchase,renderCart,rentalGuide} from './cart.js';
import {mountBanners} from './banners.js';
const main=document.querySelector('#main');
const params=new URLSearchParams(location.search);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safe=v=>{try{const u=new URL(v,location.origin);return ['https:','http:'].includes(u.protocol)?esc(u.href):''}catch{return ''}};
const won=v=>Number.isFinite(Number(v))&&v!==null?Number(v).toLocaleString('ko-KR'):'';
const money=p=>p.offers?.some(o=>o.source==='smartstore'||o.source==='imweb')?(p.sale_price??p.price):p.price;
let data,brandMap,categoryMap;
const mode=document.body.dataset.mode;
const currentBrand=()=>document.body.dataset.brand||params.get('brand')||'';
const normalize=v=>String(v??'').normalize('NFKC').toLocaleLowerCase().replace(/\s+/g,'');
const brandHref=id=>`/brands/${encodeURIComponent(id)}.html`;
function discoveryLinks(p){return `<nav class="product-tags" aria-label="관련 상품 검색">${p.discovery.tags.map(tag=>`<a href="/catalog.html?q=${encodeURIComponent(tag)}&amp;kind=${p.kind}">#${esc(tag.replace(/\s+/g,''))}</a>`).join('')}</nav>`}
function catalogHref(changes={}){const q=new URLSearchParams(location.search);q.delete('page');for(const [k,v]of Object.entries(changes)){v===null||v===''?q.delete(k):q.set(k,v)}const base=document.body.dataset.brand&&!('brand'in changes)?brandHref(document.body.dataset.brand):'/catalog.html';return base+(q.size?'?'+q.toString():'')}
function empty(title,text='',link='/catalog.html',label='전체 상품 보기'){return `<div class="empty"><h2>${esc(title)}</h2><p>${esc(text)}</p><a href="${esc(link)}">${esc(label)} →</a></div>`}
function productCard(p){const b=brandMap.get(p.brand_id);const price=money(p);const sold=p.status==='soldout';const discount=isDiscounted(p);return `<a class="product-card" href="/item.html?id=${encodeURIComponent(p.id)}"><div class="product-image"><img src="${safe(p.image)}" alt="${esc(p.name)}" loading="lazy" decoding="async" referrerpolicy="no-referrer">${sold?'<span class="badge">품절</span>':p.kind==='rental'?'<span class="badge rental">렌탈</span>':discount?'<span class="badge sale-badge">SALE</span>':isPromotion(p)?'<span class="badge sale-badge">PROMOTION</span>':''}</div><div class="product-brand">${esc(b?.name||'')}</div><h3 class="product-name">${esc(p.name)}</h3><p class="product-price">${discount?`<span class="price-before">${won(p.price)}원</span>`:''}${price===null?'가격 문의':`${won(price)}<small>원</small>`}</p>${p.kind==='rental'?'<p class="card-note">대여 상품 · 기간별 요금 확인</p>':p.status==='inquiry'?'<p class="card-note">구매·입고 상담</p>':''}</a>`}
function enhanceBrandIndex(){
 const input=document.querySelector('#brand-search');if(!input)return;
 const cards=[...document.querySelectorAll('#brand-grid>.brand-tile')];
 input.addEventListener('input',()=>{
  const q=normalize(input.value);let visible=0;
  for(const card of cards){card.hidden=!normalize(card.dataset.brandSearch||card.textContent).includes(q);if(!card.hidden)visible++}
  document.querySelector('#brand-search-status').textContent=q?`${visible}개 브랜드`:`전체 ${cards.length}개 브랜드`;
  document.querySelector('#brand-no-results').hidden=visible>0;
  document.dispatchEvent(new Event('shop:content-updated'));
 });
}
async function enhanceArtMotion(){
 const revision=document.querySelector('meta[name="catalog-revision"]').content;
 const load=src=>new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=src+'?v='+revision;script.onload=resolve;script.onerror=reject;document.head.append(script)});
 try{
  await load('/assets/shop/vendor/gsap.min.js');await load('/assets/shop/vendor/ScrollTrigger.min.js');
  const {mountArtMotion}=await import('/assets/shop/motion.js?v='+revision);
  mountArtMotion(main,{gsap:window.gsap,ScrollTrigger:window.ScrollTrigger});
 }catch(error){console.warn('Shop motion unavailable',error)}
}
function enhanceGift(){const input=document.querySelector('#gift-search');if(!input)return;const rows=[...document.querySelectorAll('.gift-category-grid>a')];input.addEventListener('input',()=>{const q=normalize(input.value);let visible=0;for(const row of rows){row.hidden=!normalize(row.textContent).includes(q);if(!row.hidden)visible++}document.querySelector('#gift-search-status').textContent=visible?`${visible}개 카테고리`:'일치하는 카테고리가 없습니다.'})}
function renderCatalog(){
 const bid=currentBrand(),brand=brandMap.get(bid);
 if(bid&&!brand){main.innerHTML=empty('브랜드를 찾을 수 없습니다.');return}
 const kind=params.get('kind')||(brand?.purchase_count===0&&brand?.rental_count>0?'rental':'purchase');
 const cat=params.get('cat')||'',type=params.get('type')||'';
 const discountOnly=params.get('sale')==='1'&&kind!=='rental';
 const benefit=['discount','promotion'].includes(params.get('benefit'))?params.get('benefit'):'all';
 const selection=catalogSelection(data,{brand:bid,kind,cat,type,sale:discountOnly,benefit});
 const applicable=selection.brandCategories,categoryCounts=selection.brandCounts;
 const relevant=c=>categoryCounts.get(c.id)||cat===c.id||isAncestor(c.id,cat);
 const roots=applicable.filter(c=>!c.parent_id&&relevant(c));
 const selectedCat=applicable.find(c=>c.id===cat);
 const catLink=(c,depth=0)=>`<a href="${esc(catalogHref({cat:c.id}))}" class="${cat===c.id?'active':''}" ${cat===c.id?'aria-current="page"':''} style="padding-left:${10+depth*8}px"><span>${esc(c.name)}</span><small>${categoryCounts.get(c.id)||0}</small></a>`;
 const nested=(c,depth=0)=>{const children=applicable.filter(x=>x.parent_id===c.id&&relevant(x));return children.length?`<details ${cat===c.id||isAncestor(c.id,cat)?'open':''}><summary>${esc(c.name)}</summary><div>${catLink(c,depth)}${children.map(x=>nested(x,depth+1)).join('')}</div></details>`:catLink(c,depth)};
 const rootOptions=applicable.filter(relevant).map(c=>`<option value="${esc(c.id)}" ${cat===c.id?'selected':''}>${'　'.repeat(Math.max(0,categoryTrail(categoryMap,c.id).length-1))}${esc(c.name)} (${categoryCounts.get(c.id)||0})</option>`).join('');
 const query=params.get('q')||'';document.querySelector('#search-input').value=query;
 const tokens=query.split(/[\s,，]+/).map(normalize).filter(Boolean);
 let filtered=selection.rows.filter(p=>(!params.has('available')||p.status!=='soldout')&&tokens.every(t=>normalize(p.name+' '+(brandMap.get(p.brand_id)?.name||'')+' '+(p.discovery?.search_terms||[]).join(' ')).includes(t)));
 const sort=params.get('sort')||'default';
 if(sort==='low'||sort==='high')filtered.sort((a,b)=>{const av=money(a),bv=money(b);if(av===null)return 1;if(bv===null)return-1;return sort==='low'?av-bv:bv-av});
 else if(sort==='name')filtered.sort((a,b)=>a.name.localeCompare(b.name,'ko'));
 else filtered.sort((a,b)=>Number(a.status==='soldout')-Number(b.status==='soldout'));
 const size=24,pages=Math.max(1,Math.ceil(filtered.length/size));const requested=Number(params.get('page'));const page=Math.min(pages,Math.max(1,Number.isFinite(requested)?Math.floor(requested):1));
 const current=filtered.slice((page-1)*size,page*size);const trail=selectedCat?categoryTrail(categoryMap,cat):[];
 const children=selectedCat?applicable.filter(c=>c.parent_id===cat&&relevant(c)):[];
 const heading=discountOnly?((brand?brand.name+' ':'')+(benefit==='promotion'?'프로모션':benefit==='discount'?'할인상품':'할인상품 · 프로모션')):brand?brand.name+(kind==='rental'?' 렌탈':''):query?`“${query}” 검색 결과`:kind==='rental'?'장비 렌탈':'전체 상품';
 const availableBrands=data.brands.filter(b=>kind==='rental'?b.rental_count>0:kind==='purchase'?b.purchase_count>0:true);
 main.innerHTML=`<div class="breadcrumb"><a href="/">홈</a><span>›</span><a href="/brands.html" target="_blank" rel="noopener">브랜드</a>${brand?`<span>›</span><a href="${esc(catalogHref({cat:null,type:null,sale:null}))}">${esc(brand.name)}</a>`:''}${trail.map((c,i)=>`<span aria-hidden="true">›</span>${i===trail.length-1?`<span aria-current="page">${esc(c.name)}</span>`:`<a href="${esc(catalogHref({cat:c.id}))}">${esc(c.name)}</a>`}`).join('')}</div>
 <div class="catalog-heading">${brand?.logo?`<img class="${brand.logo_dark?'brand-logo-dark':''}" src="${safe(brand.logo)}" alt="${esc(brand.name)}" referrerpolicy="no-referrer">`:''}<div><h1>${esc(heading)}</h1><p>제품 종류와 브랜드를 선택해 필요한 ${kind==='rental'?'대여 장비':'상품'}를 찾아보세요.</p></div></div>
 <div class="catalog-layout"><aside class="sidebar" aria-label="브랜드 및 세부 분류"><h2>브랜드 선택</h2><label class="sr" for="brand-select">브랜드 선택</label><select id="brand-select"><option value="">전체 브랜드</option>${availableBrands.map(b=>`<option value="${esc(b.id)}" ${bid===b.id?'selected':''}>${esc(b.name)} (${kind==='rental'?b.rental_count:kind==='purchase'?b.purchase_count:b.count})</option>`).join('')}</select>
 <label class="sr" for="kind-select">구매 또는 렌탈</label><select id="kind-select"><option value="purchase" ${kind==='purchase'?'selected':''}>구매 상품</option><option value="rental" ${kind==='rental'?'selected':''}>렌탈 상품</option><option value="all" ${kind==='all'?'selected':''}>구매 + 렌탈</option></select>
 ${kind!=='rental'?`<a class="sidebar-sale ${discountOnly?'active':''}" href="${esc(catalogHref({sale:'1',benefit:null,cat:null,type:null,kind:'purchase',q:null}))}" ${discountOnly?'aria-current="page"':''}><span>할인상품 · 프로모션</span><small>SALE</small></a>`:''}
 <div class="mobile-categories" style="display:none" ${applicable.length?'':'hidden'}><label class="sr" for="category-select">브랜드 세부 카테고리</label><select id="category-select"><option value="">브랜드 전체 카테고리</option>${rootOptions}</select></div>
 ${bid?`<div class="sidebar-list"><h2>${esc(brand.name)} 카테고리</h2><a href="${esc(catalogHref({cat:null}))}" class="${!cat?'active':''}">브랜드 전체 <small>${selection.base.filter(p=>!type||p.type_ids.includes(type)).length}</small></a>${roots.map(c=>nested(c)).join('')}</div>`:'<p class="brand-filter-help">브랜드를 선택하면 해당 브랜드의 세부 카테고리가 표시됩니다.</p>'}
 </aside><section class="catalog-results" aria-label="상품 목록">
 ${productTypeNavigation(selection.typeCategories,selection.typeCounts,type,id=>catalogHref({type:id}))}
 <div class="catalog-controls"><span>${selectedCat?esc(selectedCat.name)+' · ':''}총 <b>${filtered.length.toLocaleString('ko-KR')}</b>개</span><div class="filters-right"><label><input id="available-only" type="checkbox" ${params.has('available')?'checked':''}>품절 상품 제외</label><label class="sr" for="sort-select">상품 정렬</label><select id="sort-select"><option value="default">기본순</option><option value="low" ${sort==='low'?'selected':''}>낮은 가격순</option><option value="high" ${sort==='high'?'selected':''}>높은 가격순</option><option value="name" ${sort==='name'?'selected':''}>상품명순</option></select></div></div>
 ${discountOnly?benefitNavigation(benefit,key=>catalogHref({sale:'1',benefit:key==='all'?null:key,cat:null,type:null})):''}
 ${categoryControls(children,selectedCat,id=>catalogHref({cat:id}))}
 ${current.length?`<div class="product-grid">${current.map(productCard).join('')}</div>`:empty('조건에 맞는 상품이 없습니다.','제품 종류나 브랜드 분류를 바꿔 찾아보세요.',catalogHref({cat:null,type:null,q:null,available:null}),'분류 초기화')}
 <nav class="pagination" aria-label="상품 페이지">${page>1?`<a href="${esc(catalogHref({page:page-1}))}" aria-label="이전 페이지">←</a>`:''}${Array.from({length:pages},(_,i)=>i+1).filter(n=>n===1||n===pages||Math.abs(n-page)<=2).map((n,i,arr)=>`${i&&n-arr[i-1]>1?'<span aria-hidden="true">…</span>':''}<a href="${esc(catalogHref({page:n}))}" class="${n===page?'active':''}" ${n===page?'aria-current="page"':''}>${n}</a>`).join('')}${page<pages?`<a href="${esc(catalogHref({page:page+1}))}" aria-label="다음 페이지">→</a>`:''}</nav>
 </section></div>`;
 document.querySelector('#brand-select').addEventListener('change',e=>{location.href=brandSelectionHref(e.target.value,location.search,kind)});
 document.querySelector('#kind-select').addEventListener('change',e=>{location.href=catalogHref({kind:e.target.value,cat:null,type:null,sale:e.target.value==='rental'?null:params.get('sale'),benefit:e.target.value==='rental'?null:params.get('benefit')})});
 document.querySelector('#category-select').addEventListener('change',e=>{location.href=catalogHref({cat:e.target.value})});
 document.querySelector('#sort-select').addEventListener('change',e=>{location.href=catalogHref({sort:e.target.value})});
 document.querySelector('#available-only').addEventListener('change',e=>{location.href=catalogHref({available:e.target.checked?'1':null})});
}
function isAncestor(parent,child){let c=categoryMap.get(child);const seen=new Set();while(c?.parent_id&&!seen.has(c.id)){seen.add(c.id);if(c.parent_id===parent)return true;c=categoryMap.get(c.parent_id)}return false}
async function renderItem(){let id=params.get('id')||'';id=data.redirects[id]||id;const p=data.products.find(p=>p.id===id);if(!p){main.innerHTML=empty('상품을 찾을 수 없습니다.','상품이 변경되었거나 현재 판매 목록에 없습니다.');return}const response=await fetch(`/data/catalog/details/${p.detail_bucket}.json?v=${data.meta.revision}`);if(!response.ok)throw Error('상품 상세 정보를 불러오지 못했습니다.');const bucket=await response.json(),d=bucket[id];if(!d)throw Error('상품 상세 정보가 없습니다.');const brand=brandMap.get(p.brand_id);const sourceGallery=d.images?.main||[];const gallery=[...new Set([p.image.startsWith('/assets/')?p.image:(sourceGallery[0]||p.image),...sourceGallery.slice(1)])].filter(Boolean);const own=p.offers.find(o=>o.source==='smartstore')||p.offers.find(o=>o.source==='imweb');const price=money(p);const original=p.price;const sold=p.status==='soldout';const consult='https://pf.kakao.com/_pyNxnxb';const shipping=d.shipping;document.title=p.name+' | 나다운 샵';document.querySelector('link[rel="canonical"]').href=location.origin+'/item.html?id='+encodeURIComponent(id);document.querySelector('meta[property="og:title"]').content=document.title;document.querySelector('meta[property="og:image"]').content=new URL(p.image,location.origin).href;document.querySelector('meta[property="og:url"]').content=document.querySelector('link[rel="canonical"]').href;const description=p.discovery.description;document.querySelector('meta[name="description"]').content=description;document.querySelector('meta[property="og:description"]').content=description;main.innerHTML=`<div class="breadcrumb"><a href="/">홈</a><span>›</span><a href="${brandHref(p.brand_id)}">${esc(brand?.name)}</a><span>›</span><span>상품 상세</span></div><section class="detail-layout"><div><div class="gallery-main"><img id="gallery-image" src="${safe(gallery[0])}" alt="${esc(p.name)}" referrerpolicy="no-referrer"></div><div class="gallery-thumbs" aria-label="상품 이미지">${gallery.map((url,i)=>`<button type="button" class="${i===0?'active':''}" data-image="${i}" aria-label="상품 이미지 ${i+1}" aria-pressed="${i===0}"><img src="${safe(url)}" alt="" loading="lazy" referrerpolicy="no-referrer"></button>`).join('')}</div></div><div class="detail-info"><a class="detail-brand" href="${brandHref(p.brand_id)}">${esc(brand?.name)} ↗</a><h1>${esc(p.name)}</h1><div class="detail-price">${price!==null&&original>price?`<span class="price-before">${won(original)}원</span>`:''}${price===null?'가격 문의':won(price)+'<small>원</small>'}</div><dl class="product-facts"><div><dt>브랜드</dt><dd>${esc(brand?.name)}</dd></div><div><dt>상품 구분</dt><dd>${p.kind==='rental'?'장비 렌탈':'제품 구매'}</dd></div><div><dt>구매 안내</dt><dd>${sold?'품절 · 재입고 문의':own?'옵션과 수량을 선택한 뒤 주문서를 확인해주세요':p.supplier_status==='soldout'?'입고 일정 상담 후 주문':'재고 및 납기 상담 후 주문'}</dd></div>${shipping?.base_fee!==undefined?`<div><dt>기본 배송비</dt><dd>${shipping.type==='FREE'?'무료':won(shipping.base_fee)+'원'}${shipping.free_threshold?' · '+won(shipping.free_threshold)+'원 이상 무료':''}</dd></div>`:''}</dl>${d.related_variants?.length?`<details class="variant-family"><summary>이 상품의 옵션 구성 비교 (${d.related_variants.length})</summary><ul>${d.related_variants.map(v=>`<li><a href="/item.html?id=${encodeURIComponent(v.id)}" ${v.id===id?'aria-current="page"':''}>${esc(v.options.length?v.options.join(' · '):'기본 구성')}${v.id===id?' · 현재 선택':' →'}</a></li>`).join('')}</ul></details>`:''}<div id="purchase-options"></div>${p.kind==='rental'?rentalGuide():''}<div class="purchase-actions"><a class="button-outline" href="${consult}/chat" target="_blank" rel="noopener">${sold?'재입고 문의':p.kind==='rental'?'대여 일정 상담':'구매·견적 상담'} ↗</a></div><p class="purchase-help">${p.kind==='rental'?'대여 기간과 구성에 따라 금액이 달라질 수 있습니다.':'온라인 결제 오픈 준비 중입니다. 지금 구매는 상담으로 안내해드립니다.'}</p><p class="purchase-help">상품번호 ${esc(id)}</p>${discoveryLinks(p)}</div></section><nav class="detail-tabs" aria-label="상세 안내"><a href="#description">상품 상세</a><a href="#purchase-info">구매 · 배송 안내</a></nav><section class="description" id="description"><h2>상품 상세</h2>${d.description_notice?`<p class="detail-notice">${esc(d.description_notice)}</p>`:''}${d.options?.length?`<details><summary>상품 옵션 (${d.options.length})</summary><ul class="option-list">${d.options.map(o=>`<li>${esc(o.name)}${o.additional_price?' · '+(o.additional_price>0?'+':'')+won(o.additional_price)+'원':''}</li>`).join('')}</ul>`:''}${d.images?.detail?.length?d.images.detail.map((u,i)=>`<img src="${safe(u)}" alt="${esc(p.name)} 상세 정보 ${i+1}" loading="lazy" decoding="async" referrerpolicy="no-referrer">`).join(''):d.description_text?`<div class="description-text">${esc(d.description_text)}</div>`:'<p>상세 사양과 제품 구성은 구매 상담을 통해 안내해드립니다.</p>'}</section><section class="description" id="purchase-info"><h2>구매 · 배송 안내</h2><p>제품의 옵션, 재고와 납기는 상품별로 다릅니다. 정확한 구성과 배송 일정은 나다운 상담을 통해 확인해주세요. <a href="/shipping.html">배송·교환·반품 전체 안내 →</a></p><p style="margin-top:15px">장비 문의 <a href="tel:0507-1394-6231">0507-1394-6231</a> · <a href="${consult}" target="_blank" rel="noopener">카카오톡 상담 ↗</a></p></section>`;mountPurchase(p,d);document.querySelectorAll('[data-image]').forEach(button=>button.addEventListener('click',()=>{document.querySelector('#gallery-image').src=gallery[Number(button.dataset.image)];document.querySelectorAll('[data-image]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button))})}));}
function renderCategories(){if(!data.meta.category_browsing_enabled){main.innerHTML=`<div class="breadcrumb"><a href="/">홈</a><span>›</span><span>카테고리</span></div>${empty('브랜드별로 장비를 찾아보세요.','제품 종류별 통합 카테고리는 준비 중입니다.','/brands.html','브랜드 전체 보기')}`;return}renderCatalog()}
document.addEventListener('error',event=>{
  const image=event.target;
  if(!(image instanceof HTMLImageElement)||!main.contains(image))return;
  const brand=image.closest('.brand-word,.brand-visual');
  if(brand){brand.textContent=image.alt;return}
  if(image.closest('.description')){
    const notice=document.createElement('p');
    notice.textContent='일부 상세 이미지를 불러오지 못했습니다. 상담 채널에서 제품 정보를 문의해주세요.';
    image.replaceWith(notice);
    return;
  }
  image.style.visibility='hidden';
  const holder=image.closest('.product-image,.gallery-main,.gallery-thumbs button,.cart-image');
  if(holder){holder.classList.add('image-fallback');holder.setAttribute('aria-label','상품 이미지 준비 중')}
},true);
document.addEventListener('load',event=>{
  const image=event.target;
  if(!(image instanceof HTMLImageElement)||!main.contains(image))return;
  image.style.visibility='';
  const holder=image.closest('.image-fallback');
  if(holder){holder.classList.remove('image-fallback');holder.removeAttribute('aria-label')}
},true);
if(mode==='gift')enhanceGift();
if(mode==='brands')enhanceBrandIndex();
if(!['policy','guide','gift','about','studio','home','brands'].includes(mode))try{const revision=document.querySelector('meta[name="catalog-revision"]').content;const response=await fetch(`/data/catalog/${["catalog","categories"].includes(mode)&&params.get("kind")==="rental"?"rental":"catalog"}.json?v=${revision}`);if(!response.ok)throw Error('상품 목록을 불러오지 못했습니다.');data=await response.json();brandMap=new Map(data.brands.map(b=>[b.id,b]));categoryMap=new Map((data.categories||[]).map(c=>[c.id,c]));if(mode==='item')await renderItem();else if(mode==='cart'||mode==='checkout')await renderCart(data,mode==='checkout');else if(mode==='categories')renderCategories();else renderCatalog();}catch(error){console.error(error);main.innerHTML=empty('잠시 상품을 불러오지 못했습니다.','새로고침 후 다시 확인해주세요.','https://smartstore.naver.com/rainbowbene','스마트스토어에서 상품 보기')}

if(mode==='home')mountBanners(document.querySelector('.shop-banner'));
if(mode!=='policy')enhanceArtMotion();
