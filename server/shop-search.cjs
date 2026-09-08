const fs=require('node:fs');
const path=require('node:path');
const gift=require('./gift-catalog.cjs');
const catalog=JSON.parse(fs.readFileSync(path.join(process.cwd(),'data/catalog/catalog.json'),'utf8'));
const brandMap=new Map(catalog.brands.map(b=>[b.id,b]));
const categoryMap=new Map(catalog.categories.map(c=>[c.id,c]));
const index=catalog.products.filter(p=>!p.listing_id||p.listing_id===p.id).map(p=>({p,text:gift.normalize([
 p.id,p.name,brandMap.get(p.brand_id)?.name,...(brandMap.get(p.brand_id)?.aliases||[]),
 ...p.type_ids.map(id=>categoryMap.get(id)?.name)].join(' '))}));
const labels={all:'전체',purchase:'제품 구매',rental:'제품 렌탈',gift:'기프트 구매'};
function url(q,scope='all',page=1){const p=new URLSearchParams({q});if(scope!=='all')p.set('scope',scope);if(page>1)p.set('page',page);return '/search.html?'+p;}
function card(p){
 if(p.search_kind==='gift')return gift.card(p);
 const price=p.offers.some(o=>['smartstore','imweb'].includes(o.source))?(p.sale_price??p.price):p.price;
 return `<a class="product-card" href="/item.html?id=${encodeURIComponent(p.id)}"><div class="product-image"><img src="${gift.esc(p.image)}" alt="${gift.esc(p.name)}" loading="lazy" referrerpolicy="no-referrer">${p.status==='soldout'?'<span class="badge">품절</span>':p.kind==='rental'?'<span class="badge rental">렌탈</span>':''}</div><p class="product-brand">${gift.esc(brandMap.get(p.brand_id)?.name)}</p><h3 class="product-name">${gift.esc(p.name)}</h3><p class="product-price">${price==null?'가격 문의':price.toLocaleString('ko-KR')+'원'}${p.kind==='rental'?' <small>/ 대여료</small>':''}</p></a>`;
}
function results(q){
 const words=gift.tokens(q);
 if(!words.length)return [];
 const equipment=index.filter(r=>words.every(w=>r.text.includes(w))).map(({p})=>({...p,search_kind:p.kind}));
 const gifts=gift.find(q).map(p=>({...p,search_kind:'gift'}));
 const needle=gift.normalize(q);
 return [...equipment,...gifts].sort((a,b)=>{
  const rank=p=>p.id===q?0:gift.normalize(p.name)===needle?1:gift.normalize(p.name).startsWith(needle)?2:3;
  return rank(a)-rank(b);
 });
}
function render(params){
 const q=(params.get('q')||'').trim().slice(0,120),scope=Object.hasOwn(labels,params.get('scope'))?params.get('scope'):'all';
 const found=results(q),counts={all:found.length,purchase:0,rental:0,gift:0};
 for(const p of found)counts[p.search_kind]++;
 const selected=found.filter(p=>scope==='all'||p.search_kind===scope),page=gift.queryPage(params,selected.length);
 if(page===null)return {status:404,title:'검색 페이지를 찾을 수 없습니다',body:'<h1>페이지를 찾을 수 없습니다.</h1><a href="/search.html">다시 검색하기</a>'};
 const body=`<section class="search-directory"><div class="catalog-heading"><h1>통합 검색</h1><p>제품 구매·렌탈·기프트 상품을 한 번에 찾아보세요.</p></div><form class="unified-search-form" action="/search.html" method="get"><label class="sr" for="all-products-query">전체 상품 검색</label><input id="all-products-query" name="q" type="search" value="${gift.esc(q)}" placeholder="상품명, 브랜드, 종류, 상품번호" maxlength="120"><button type="submit">검색</button></form><nav class="search-scopes" aria-label="검색 상품 종류">${Object.entries(labels).map(([k,label])=>`<a href="${gift.esc(url(q,k))}" ${scope===k?'aria-current="page"':''}>${label}<span>${counts[k].toLocaleString('ko-KR')}</span></a>`).join('')}</nav>${q?`<p class="search-result-count">‘${gift.esc(q)}’ 검색 결과 <strong>${selected.length.toLocaleString('ko-KR')}개</strong></p>`:''}${selected.length?`<div class="product-grid">${selected.slice((page-1)*48,page*48).map(card).join('')}</div>${gift.pagination(selected.length,page,n=>url(q,scope,n))}`:`<div class="empty"><h2>${q?'일치하는 상품이 없습니다.':'어떤 상품을 찾으세요?'}</h2><p>${q?'다른 이름이나 상품번호로 검색해 보세요.':'텀블러, 삼각대, 조명, 브랜드명으로 검색해 보세요.'}</p><a href="/catalog.html?kind=purchase">제품 구매</a> · <a href="/catalog.html?kind=rental">제품 렌탈</a> · <a href="/gifts.html">기프트 구매</a></div>`}</section>`;
 return {status:200,title:(q?q+' 검색':'통합 검색')+' | 나다운 샵',description:'촬영장비 구매·렌탈부터 기프트·굿즈까지. 나다운 샵 전체 상품을 상품명, 브랜드와 종류로 검색하세요.',canonical:'https://shop.nadaun.co'+url(q,scope,page),noindex:true,body,counts};
}
module.exports={render,results};
