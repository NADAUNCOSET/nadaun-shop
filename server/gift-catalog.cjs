const fs=require('node:fs');
const path=require('node:path');
const root=process.cwd(), origin='https://shop.nadaun.co';
const data=JSON.parse(fs.readFileSync(path.join(root,'data/gift/catalog.json'),'utf8'));
const categories=new Map(data.categories.map(c=>[c.id,c]));
const products=new Map(data.products.map(p=>[p.id,p]));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const normalize=v=>String(v??'').normalize('NFKC').toLocaleLowerCase().replace(/타월/g,'타올').replace(/에코백/g,'에코가방').replace(/\s+/g,'');
const indexed=data.products.map(p=>({p,text:normalize([p.id,p.name,...p.category_ids.map(id=>categories.get(id)?.name)].join(' '))}));
function tokens(query){return String(query||'').trim().slice(0,120).split(/\s+/).filter(Boolean).map(normalize);}
function find(query='',category=''){
 const words=tokens(query);
 return indexed.filter(({p,text})=>(!category||p.category_ids.includes(category))&&words.every(w=>text.includes(w))).map(x=>x.p);
}
function href(params={},anchor=''){
 const query=new URLSearchParams(Object.entries(params).filter(([,v])=>v!==''&&v!==null&&v!==undefined));
 return '/gifts.html'+(query.size?'?'+query:'')+anchor;
}
function kinds(){return '<nav class="browse-kinds" aria-label="쇼핑 목적"><a href="/catalog.html?kind=purchase">제품 구매</a><a href="/catalog.html?kind=rental">제품 렌탈</a><a href="/gifts.html" aria-current="page">기프트 구매</a></nav>';}
function tile(c){return `<a class="category-image-tile" href="${esc(href({category:c.id}))}"><span class="category-image"><img src="${esc(c.image)}" alt="" width="154" height="135" loading="lazy" decoding="async" referrerpolicy="no-referrer"></span><strong>${esc(c.name)}</strong></a>`;}
function card(p){return `<a class="product-card gift-product-card" href="/gift-item.html?id=${p.id}"><div class="product-image"><img src="${esc(p.image)}" alt="${esc(p.name)}" loading="lazy" decoding="async" referrerpolicy="no-referrer">${p.soldout?'<span class="badge">품절</span>':''}</div><h3 class="product-name">${esc(p.name)}</h3><p class="card-note">상품번호 ${p.id}</p><p class="product-price">${p.soldout?'재입고 문의':'수량별 견적'}</p></a>`;}
function pagination(total,page,url){
 const pages=Math.max(1,Math.ceil(total/48));if(pages===1)return '';
 const nums=[...new Set([1,...Array.from({length:5},(_,i)=>page-2+i).filter(n=>n>1&&n<pages),pages])].sort((a,b)=>a-b);
 return `<nav class="pagination" aria-label="상품 페이지">${page>1?`<a href="${esc(url(page-1))}" aria-label="이전 페이지">←</a>`:''}${nums.map((n,i)=>(i&&n-nums[i-1]>1?'<span>…</span>':'')+`<a href="${esc(url(n))}" ${n===page?'aria-current="page"':''}>${n}</a>`).join('')}${page<pages?`<a href="${esc(url(page+1))}" aria-label="다음 페이지">→</a>`:''}</nav>`;
}
function queryPage(params,total){const raw=params.get('page')||'1';if(!/^[1-9]\d{0,5}$/.test(raw))return null;const n=Number(raw);return n<=Math.max(1,Math.ceil(total/48))?n:null;}
function directory(params){
 const category=params.get('category')||'',q=(params.get('q')||'').trim().slice(0,120),selected=categories.get(category);
 if(category&&!selected)return {status:404,title:'카테고리를 찾을 수 없습니다',body:'<h1>카테고리를 찾을 수 없습니다.</h1><a href="/gifts.html">기프트 전체보기</a>'};
 const rows=find(q,category),page=queryPage(params,rows.length);
 if(page===null)return {status:404,title:'페이지를 찾을 수 없습니다',body:'<h1>페이지를 찾을 수 없습니다.</h1><a href="/gifts.html">기프트 전체보기</a>'};
 const roots=data.categories.filter(c=>!c.parent_ids.length);
 const top=selected?(selected.parent_ids.length?data.categories.filter(c=>c.parent_ids.some(id=>selected.parent_ids.includes(id))):data.categories.filter(c=>c.parent_ids.includes(category))):roots;
 const parent=selected?.parent_ids[0];
 const trail=selected?`<span>›</span>${parent?`<a href="${href({category:parent})}">${esc(categories.get(parent).name)}</a><span>›</span>`:''}<span aria-current="page">${esc(selected.name)}</span>`:'';
 const children=selected?.parent_ids.length?[]:top;
 const tiles=children.length?children:top;
 const allKinds=`<details class="gift-all-types"><summary>세부 종류 전체보기 <span>${data.meta.leaf_category_count}개</span></summary><div class="gift-type-groups">${roots.map(r=>`<section><h3><a href="${href({category:r.id})}">${esc(r.name)}</a></h3><div>${data.categories.filter(c=>c.parent_ids.includes(r.id)).map(c=>`<a href="${href({category:c.id})}">${esc(c.name)} <small>${c.count.toLocaleString('ko-KR')}</small></a>`).join('')}</div></section>`).join('')}</div></details>`;
 const heading=selected?selected.name+' 종류':'기프트 종류';
 const body=`<div class="breadcrumb"><a href="/">홈</a><span>›</span><a href="/gifts.html">기프트 구매</a>${trail}</div><section class="catalog-heading gift-heading"><h1>기프트 구매</h1><p>필요한 종류를 고르고, 수량과 인쇄에 맞는 상품을 찾아보세요.</p></section>${kinds()}<section class="category-gallery gift-directory"><div class="section-head"><div><h2>${esc(heading)}로 찾기</h2><p>생활용품부터 문구, 텀블러, 단체 선물까지.</p></div><a class="text-button" href="#gift-products">상품 바로 보기 ↓</a></div>${selected?`<a class="gift-back" href="${href({category:parent||''})}">← ${parent?'상위 종류':'전체 종류'}</a>`:''}<nav class="category-image-grid" aria-label="기프트 종류 선택">${tiles.map(tile).join('')}</nav>${allKinds}</section><section id="gift-products"><div class="gift-product-tools"><div><h2>${esc(selected?.name||'전체 기프트 상품')}</h2><p>총 <strong>${rows.length.toLocaleString('ko-KR')}</strong>개${q?' · '+esc(q)+' 검색 결과':''}</p></div><form action="/gifts.html#gift-products" method="get" class="gift-search-form">${category?`<input type="hidden" name="category" value="${esc(category)}">`:''}<label class="sr" for="gift-query">기프트 상품명 또는 상품번호</label><input id="gift-query" name="q" type="search" value="${esc(q)}" placeholder="상품명 또는 상품번호" maxlength="120"><button type="submit">검색</button></form></div>${rows.length?`<div class="product-grid">${rows.slice((page-1)*48,page*48).map(card).join('')}</div>`:`<div class="empty"><h2>일치하는 상품이 없습니다.</h2><p>다른 상품명이나 상품번호로 검색해 보세요.</p><a href="${href({category})}">검색 초기화</a></div>`}${pagination(rows.length,page,n=>href({category,q,page:n},'#gift-products'))}</section>`;
 return {status:200,title:(selected?.name||'기프트 구매')+' | 나다운 샵',description:'기프트·굿즈를 종류별로 찾아보세요. 상품명·상품번호 검색과 수량·인쇄 상담을 나다운 샵에서 한 번에.',canonical:origin+href({category,q,page:page>1?page:null}),noindex:!!q,body,rows,page};
}
function detail(id){
 const p=products.get(id);if(!p)return {status:404,title:'상품을 찾을 수 없습니다',body:'<h1>상품을 찾을 수 없습니다.</h1><a href="/gifts.html">기프트 전체보기</a>'};
 const bucket=path.join(root,'data/gift/details', (Number(id)%256).toString(16).padStart(2,'0')+'.json');
 const d=p.detail_available?JSON.parse(fs.readFileSync(bucket,'utf8'))[id]:null;
 if(p.detail_available&&!d)throw Error('Verified gift detail missing');
 const leaf=categories.get(p.category_ids.at(-1));
 const specs=(d?.specifications||[]).map(s=>`<tr><th scope="row">${esc(s.name)}</th><td>${esc(s.value)}</td></tr>`).join('');
 const choices=(d?.choices||[]).map(s=>Object.values(s).filter(Boolean).join(' / ')).filter(Boolean);
 const images=[...new Set([p.image,...(d?.images||[])])];
 const body=`<div class="breadcrumb"><a href="/">홈</a><span>›</span><a href="/gifts.html">기프트 구매</a><span>›</span><a href="${href({category:leaf.id})}">${esc(leaf.name)}</a></div>${kinds()}<section class="detail-layout gift-detail"><div class="gallery-main"><img src="${esc(images[0])}" alt="${esc(p.name)}" fetchpriority="high" referrerpolicy="no-referrer"></div><div class="detail-info"><p class="detail-brand">상품번호 ${p.id}</p><h1>${esc(p.name)}</h1><p class="detail-price">${p.soldout?'품절 · 재입고 문의':'수량별 견적'}</p><p class="purchase-help">수량, 인쇄와 포장에 따라 판매가격이 달라집니다. 원하시는 제작 조건을 알려주세요.</p>${d?.minimum_quantity?`<p class="gift-minimum">기본 주문 수량 <strong>${Number(d.minimum_quantity).toLocaleString('ko-KR')}개</strong> · 소량 주문 별도 상담</p>`:''}${choices.length?`<details class="gift-choice-list"><summary>선택 가능한 사양 보기</summary><ul>${choices.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}<div class="gift-detail-actions"><a class="button-primary" href="https://pf.kakao.com/_pyNxnxb/chat" target="_blank" rel="noopener">수량·인쇄 상담</a><a class="button-outline" href="https://talk.naver.com/ct/w4w1o8" target="_blank" rel="noopener">네이버 톡톡 상담</a></div><p class="gift-reference">상담하실 때 상품번호 <strong>${p.id}</strong>를 알려주세요.</p><a class="text-button" href="${href({category:leaf.id})}">같은 종류 상품 보기 →</a></div></section><section class="gift-description"><h2>상품 상세</h2>${specs?`<table><tbody>${specs}</tbody></table>`:''}${d?images.slice(1).map(u=>`<img src="${esc(u)}" alt="${esc(p.name)} 상세 이미지" loading="lazy" decoding="async" referrerpolicy="no-referrer">`).join(''):'<p>상세 사양과 인쇄 가능 범위는 상품번호로 문의해 주세요.</p>'}</section>`;
 const description=(p.name+' · 기프트·굿즈 수량별 견적과 인쇄 상담. 나다운 샵.').slice(0,80);
 return {status:200,title:p.name+' | 나다운 샵',description,canonical:origin+'/gift-item.html?id='+p.id,image:p.image,body,
  schema:{'@context':'https://schema.org','@type':'Product',name:p.name,sku:p.id,image:images.slice(0,5),description,category:leaf.name,url:origin+'/gift-item.html?id='+p.id}};
}
function page(template,result){
 let html=template.replace(/<title>.*?<\/title>/,()=>`<title>${esc(result.title)}</title>`)
  .replace(/(<meta (?:name="description"|property="og:description") content=")[^"]*"/g,(_,p)=>p+esc(result.description||result.title)+'"')
  .replace(/(<meta property="og:title" content=")[^"]*"/,(_,p)=>p+esc(result.title)+'"')
  .replace(/(<meta property="og:url" content=")[^"]*"/,(_,p)=>p+esc(result.canonical||origin+'/gifts.html')+'"')
  .replace(/(<link rel="canonical" href=")[^"]*"/,(_,p)=>p+esc(result.canonical||origin+'/gifts.html')+'"')
  .replace(/(<main id="main"[^>]*>)[\s\S]*?<\/main>/,(_,p)=>p+result.body+'</main>');
 if(result.image)html=html.replace(/(<meta property="og:image" content=")[^"]*"/,(_,p)=>p+esc(result.image)+'"');
 if(result.noindex||result.status!==200)html=html.replace('index,follow,max-image-preview:large','noindex,follow');
 if(result.schema)html=html.replace('</head>',()=>'<script type="application/ld+json">'+JSON.stringify(result.schema).replace(/</g,'\\u003c')+'</script></head>');
 return html;
}
module.exports={data,categories,products,esc,normalize,tokens,find,card,pagination,queryPage,directory,detail,page};
