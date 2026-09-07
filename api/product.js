const fs=require('node:fs');
const path=require('node:path');
const base=process.cwd();
const catalog=JSON.parse(fs.readFileSync(path.join(base,'data/catalog/catalog.json'),'utf8'));
const template=fs.readFileSync(path.join(base,'item.html'),'utf8');
const products=new Map(catalog.products.map(p=>[p.id,p]));
const brands=new Map(catalog.brands.map(b=>[b.id,b]));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const origin='https://shop.nadaun.co';
module.exports=function handler(req,res){
 if(!['GET','HEAD'].includes(req.method)){res.setHeader('Allow','GET, HEAD');return res.status(405).end('Method not allowed');}
 const id=new URL(req.url,origin).searchParams.get('id');
 const primary=catalog.redirects[id];
 if(primary){res.setHeader('Location','/item.html?id='+encodeURIComponent(primary));return res.status(308).end();}
 const p=products.get(id);
 res.setHeader('Content-Type','text/html; charset=utf-8');
 if(!p){res.setHeader('X-Robots-Tag','noindex');return res.status(404).end('<!doctype html><html lang="ko"><meta charset="utf-8"><title>상품을 찾을 수 없습니다 | 나다운 샵</title><h1>상품을 찾을 수 없습니다.</h1><a href="/catalog.html">전체 상품 보기</a></html>');}
 const brand=brands.get(p.brand_id)?.name||'';
 const canonical=origin+'/item.html?id='+encodeURIComponent(p.id);
 const title=p.name+' | 나다운 샵';
 const description=p.discovery.description;
 const image=new URL(p.image,origin).href;
 const price=p.offers.some(o=>['smartstore','imweb'].includes(o.source))?(p.sale_price??p.price):p.price;
 const schema={'@context':'https://schema.org','@type':'Product',name:p.name,description,image:[image],sku:p.id,url:canonical,brand:{'@type':'Brand',name:brand},category:p.discovery.categories.join(' / '),keywords:p.discovery.tags.join(', ')};
 // Do not invent ratings, availability, shipping terms or a live checkout offer.
 const tags=`<nav class="product-tags" aria-label="관련 상품 검색">${p.discovery.tags.map(tag=>`<a href="/catalog.html?q=${encodeURIComponent(tag)}&amp;kind=${p.kind}">#${esc(tag.replace(/\s+/g,''))}</a>`).join('')}</nav>`;
 const body=`<div class="breadcrumb"><a href="/">홈</a><span>›</span><a href="/brands/${esc(p.brand_id)}.html">${esc(brand)}</a><span>›</span>상품 상세</div><section class="detail-layout"><div class="gallery-main"><img src="${esc(image)}" alt="${esc(p.name)}" referrerpolicy="no-referrer"></div><div class="detail-info"><a class="detail-brand" href="/brands/${esc(p.brand_id)}.html">${esc(brand)}</a><h1>${esc(p.name)}</h1><p class="detail-price">${price===null?'가격 문의':Number(price).toLocaleString('ko-KR')+'원'}</p><p class="purchase-help">${p.kind==='rental'?'장비 렌탈 · 대여 기간별 요금을 확인해주세요.':p.status==='soldout'?'품절 · 재입고 문의':'옵션과 재고·납기는 상품별로 확인해주세요.'}</p><a class="button-outline" href="https://pf.kakao.com/_pyNxnxb/chat" target="_blank" rel="noopener">구매·렌탈 상담</a><p><a href="/shipping.html">배송·교환·반품 안내</a></p>${tags}</div></section>`;
 let html=template.replace(/<title>.*?<\/title>/,()=>`<title>${esc(title)}</title>`)
 .replace(/(<meta name="description" content=")[^"]*"/,(_,prefix)=>prefix+esc(description)+'"')
 .replace(/(<meta property="og:title" content=")[^"]*"/,(_,prefix)=>prefix+esc(title)+'"')
 .replace(/(<meta property="og:description" content=")[^"]*"/,(_,prefix)=>prefix+esc(description)+'"')
 .replace(/(<meta property="og:image" content=")[^"]*"/,(_,prefix)=>prefix+esc(image)+'"')
 .replace(/(<meta property="og:url" content=")[^"]*"/,(_,prefix)=>prefix+esc(canonical)+'"')
 .replace(/(<link rel="canonical" href=")[^"]*"/,(_,prefix)=>prefix+esc(canonical)+'"')
 .replace('noindex,follow','index,follow,max-image-preview:large')
 .replace(/(<main id="main"[^>]*>)[\s\S]*?<\/main>/,(_,prefix)=>prefix+body+'</main>')
 .replace('</head>',()=>`<script type="application/ld+json">${JSON.stringify(schema).replace(/</g,'\\u003c')}</script></head>`);
 res.setHeader('Cache-Control','public, max-age=0, s-maxage=300');
 return res.status(200).end(req.method==='HEAD'?'':html);
};
