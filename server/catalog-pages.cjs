// Share the exact browser selection rules, and deliver their contents before JS.
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {esc}=require('./share-metadata.cjs');
const matching=require('../assets/shop/product-search.js');
const rental=require('../assets/shop/rental-content.js');
const origin='https://shop.nadaun.co';
let toolsPromise;
function tools(){return toolsPromise||(toolsPromise=import(pathToFileURL(path.join(__dirname,'../assets/shop/catalog-tools.js')).href));}
function amount(p){return p.release_status==='coming_soon'?null:p.offers.some(o=>['smartstore','imweb'].includes(o.source))?(p.sale_price??p.price):p.price;}
function card(p,brand){
 const price=amount(p),label=p.release_status==='coming_soon'?'출시 예정 · 가격 미공개':p.kind==='rental'?rental.priceHTML(p):price===null?'가격 문의':Number(price).toLocaleString('ko-KR')+'원';
 return `<a class="product-card" href="/item.html?id=${encodeURIComponent(p.id)}"><div class="product-image"><img src="${esc(p.image)}" alt="${esc(p.name)}" loading="lazy" referrerpolicy="no-referrer"></div><p class="product-brand">${esc(brand?.name)}</p><h3 class="product-name">${esc(p.name)}</h3><p class="product-price">${label}</p></a>`;
}
async function render(catalog,params,brandId='',pathname='/catalog.html'){
 const t=await tools(),brands=new Map(catalog.brands.map(b=>[b.id,b])),categories=new Map(catalog.categories.map(c=>[c.id,c]));
 const brand=brands.get(brandId),kind=params.get('kind')||(brand?.purchase_count===0&&brand?.rental_count>0?'rental':'purchase');
 const error=()=>({status:404,noindex:true,title:'상품 목록을 찾을 수 없습니다 | 나다운 스페이스',body:'<h1>상품 목록을 찾을 수 없습니다.</h1><a href="/catalog.html">전체 상품 보기</a>'});
 if((brandId&&!brand)||!['purchase','rental','all'].includes(kind))return error();
 const type=params.get('type')||'',cat=catalog.category_redirects?.[params.get('cat')]||params.get('cat')||'';
 if((type&&!categories.has(type))||(cat&&!categories.has(cat)))return error();
 const camera=params.get('camera')||'',selectedCamera=(catalog.camera_models||[]).find(m=>m.id===camera);
 if(camera&&!selectedCamera)return error();
 const sale=params.get('sale')==='1'&&kind!=='rental',benefit=['discount','promotion'].includes(params.get('benefit'))?params.get('benefit'):'all';
 const selected=t.catalogSelection(catalog,{brand:brandId,kind,type,cat,sale,benefit,collection:params.get('collection')||'',camera});
 if(type&&!selected.typeCategories.some(c=>c.id===type))return error();
 const q=(params.get('q')||'').trim().slice(0,120),tokens=matching.tokens(q),sort=params.get('sort')||'default';
 const rows=selected.rows.filter(p=>(!params.has('available')||(p.status!=='soldout'&&p.release_status!=='coming_soon'))&&tokens.every(w=>matching.normalize(p.name+' '+(brands.get(p.brand_id)?.name||'')+' '+(p.discovery?.search_terms||[]).join(' ')).includes(w)));
 if(sort==='low'||sort==='high')rows.sort((a,b)=>{const x=amount(a),y=amount(b);return x===null?1:y===null?-1:sort==='low'?x-y:y-x;});
 else if(sort==='name')rows.sort((a,b)=>a.name.localeCompare(b.name,'ko'));
 else rows.sort(t.catalogDefaultOrder(brand));
 const raw=params.get('page')||'1',pages=Math.max(1,Math.ceil(rows.length/24));
 if(!/^[1-9]\d{0,5}$/.test(raw)||Number(raw)>pages)return error();
 const page=Number(raw),current=rows.slice((page-1)*24,page*24);
 const href=(changes={})=>{
  const v=new URLSearchParams(params);v.delete('view');v.delete('brand');v.delete('page');
  for(const [k,value]of Object.entries(changes)){value===null||value===''?v.delete(k):v.set(k,value);}
  return pathname+(v.size?'?'+v:'');
 };
 const intent=kind==='rental'?'카메라 대여·렌즈·조명 렌탈':'카메라·렌즈·조명 구매';
 const subject=[brand?.name,categories.get(type)?.name,categories.get(selected.selectedCategory)?.name].filter(Boolean).join(' · ');
 const heading=q?'“'+q+'” 검색 결과':selectedCamera?selectedCamera.name+'용 케이지·액세서리':(subject?subject+' · ':'')+intent;
 const title=heading+(page>1?' · '+page+'페이지':'')+' | 나다운 스페이스';
 const canonicalParams=new URLSearchParams();
 if(kind!=='purchase')canonicalParams.set('kind',kind);
 if(camera)canonicalParams.set('camera',camera);
 if(type)canonicalParams.set('type',type);
 if(selected.selectedCategory)canonicalParams.set('cat',selected.selectedCategory);
 if(page>1)canonicalParams.set('page',page);
 const canonical=origin+pathname+(canonicalParams.size?'?'+canonicalParams:'');
 const navigation=t.productTypeNavigation(selected.typeCategories,selected.typeCounts,type,id=>href({type:id,page:null}),{hideEmpty:!!brand});
 const brandCategories=selected.brandCategories.filter(c=>selected.brandCounts.get(c.id)>0);
 const nativeCategories=brandCategories.length?`<details class="product-types-all"><summary>${esc(brand.name)} 세부 카테고리</summary><nav class="category-chips" aria-label="브랜드 세부 카테고리">${brandCategories.map(c=>`<a href="${esc(href({cat:c.id}))}">${esc(c.name)}</a>`).join('')}</nav></details>`:'';
 const nums=[...new Set([1,...Array.from({length:5},(_,i)=>page-2+i).filter(n=>n>1&&n<pages),pages])].sort((a,b)=>a-b);
 const pagination=pages>1?`<nav class="pagination" aria-label="상품 페이지">${page>1?`<a href="${esc(href({page:page-1}))}" aria-label="이전 페이지">←</a>`:''}${nums.map(n=>`<a href="${esc(href({page:n}))}" ${n===page?'aria-current="page"':''}>${n}</a>`).join('')}${page<pages?`<a href="${esc(href({page:page+1}))}" aria-label="다음 페이지">→</a>`:''}</nav>`:'';
 const description=[subject,intent+' 상품의 모델·옵션·구성을 확인하세요.',kind==='rental'?'영등포 나다운 스페이스에서 대여 기간과 픽업·반납을 상담하세요.':'나다운 스페이스에서 재고와 납기·구매 견적을 상담하세요.'].filter(Boolean).join(' ');
 const body=`<div class="breadcrumb"><a href="/">홈</a><span>›</span><a href="/brands.html">촬영장비 브랜드</a></div><section class="catalog-heading"><div><h1>${esc(heading)}</h1><p>${esc(description)}</p></div></section><nav class="browse-kinds" aria-label="쇼핑 목적"><a href="/catalog.html">제품 구매</a><a href="/catalog.html?kind=rental">제품 렌탈</a><a href="/gifts.html">기프트 구매</a></nav>${navigation}${nativeCategories}<p>총 ${rows.length.toLocaleString('ko-KR')}개 · ${page}/${pages}페이지</p>${current.length?`<div class="product-grid">${current.map(p=>card(p,brands.get(p.brand_id))).join('')}</div>`:'<p>조건에 맞는 상품이 없습니다. <a href="/catalog.html">전체 상품 보기</a></p>'}${pagination}`;
 return {status:200,title,description,canonical,noindex:!!q||params.has('sort')||params.has('available')||sale||params.has('collection'),body,rows:current,total:rows.length,page,brandId,
 schema:{'@context':'https://schema.org','@type':'CollectionPage',name:title,url:canonical,description,inLanguage:'ko-KR',mainEntity:{'@type':'ItemList',itemListElement:current.map((p,i)=>({'@type':'ListItem',position:(page-1)*24+i+1,name:p.name,url:origin+'/item.html?id='+encodeURIComponent(p.id)}))}}};
}
function createHandler({catalog,template}){
 const gift=require('./gift-catalog.cjs');
 // The request-specific collection replaces the static page graph, not Store identity.
 template=template.replace(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g,(all,json)=>{try{return JSON.parse(json)['@graph']?'':all;}catch{return all;}});
 return async function(req,res){
  if(!['GET','HEAD'].includes(req.method)){res.setHeader('Allow','GET, HEAD');return res.status(405).end();}
  const url=new URL(req.url,origin),brandId=(url.pathname.match(/^\/brands\/([a-z0-9-]+)\.html$/)||[])[1]||url.searchParams.get('brand')||req.query?.brand||'';
  const pathname=brandId?'/brands/'+brandId+'.html':url.pathname==='/catalog_category.html'?'/catalog_category.html':'/catalog.html';
  const result=await render(catalog,url.searchParams,brandId,pathname);
  let html=gift.page(template,result).replace('data-brand=""','data-brand="'+esc(brandId)+'"');
  res.setHeader('Content-Type','text/html; charset=utf-8');res.setHeader('Cache-Control','public, max-age=0, s-maxage=60');
  if(result.noindex||result.status!==200)res.setHeader('X-Robots-Tag','noindex');
  return res.status(result.status).end(req.method==='HEAD'?'':html);
 };
}
module.exports={render,createHandler};
