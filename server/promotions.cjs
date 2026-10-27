const {esc}=require('./share-metadata.cjs');
function activeCampaigns(product,now){
 if(product.kind!=='purchase'||product.release_status==='coming_soon')return [];
 return (product.promotions||[]).filter(c=>Date.parse(c.start_at)<=now&&now<Date.parse(c.end_at));
}
function render(catalog,now){
 const families=new Map();
 for(const p of catalog.products){if(!activeCampaigns(p,now).length)continue;const id=p.listing_id||p.id;if(!families.has(id)||p.id===id)families.set(id,p);}
 const rows=[...families.values()];
 const campaigns=new Map(rows.flatMap(p=>activeCampaigns(p,now)).map(c=>[c.id,c]));
 const date=value=>new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
 const events=[...campaigns.values()].map(c=>`<article class="detail-notice"><strong>${esc(c.title)}</strong><p>${esc(date(c.start_at))} ~ ${esc(date(Date.parse(c.end_at)-1))}</p><p>${esc(c.terms)}</p></article>`).join('');
 const cards=rows.slice(0,24).map(p=>{
  const amount=p.offers?.some(o=>['smartstore','imweb'].includes(o.source))?(p.sale_price??p.price):p.price;
  return `<a class="product-card" href="/item.html?id=${encodeURIComponent(p.id)}"><div class="product-image"><img src="${esc(p.image)}" alt="${esc(p.name)}" loading="lazy" referrerpolicy="no-referrer"></div><h2 class="product-name">${esc(p.name)}</h2><p class="product-price">${amount===null?'가격 문의':Number(amount).toLocaleString('ko-KR')+'원'}</p></a>`;
 }).join('');
 return `<div class="breadcrumb"><a href="/">홈</a><span>›</span>프로모션</div><div class="catalog-heading"><div><h1>프로모션</h1><p>기간별 혜택과 대상 상품, 행사 조건을 확인하세요.</p></div></div>${events?`<section class="promotion-campaigns" aria-label="진행 중인 행사">${events}</section>`:''}${rows.length?`<p>총 ${rows.length}개</p><div class="product-grid">${cards}</div>`:'<div class="empty"><h2>진행 중인 프로모션이 없습니다.</h2><p>새로운 행사가 확인되면 안내해 드립니다.</p><a href="/catalog.html">전체 상품 보기 →</a></div>'}`;
}
function createHandler({catalog,template,clock=Date.now}){
 return function(req,res){
  if(!['GET','HEAD'].includes(req.method)){res.setHeader('Allow','GET, HEAD');return res.status(405).end();}
  const html=template.replace(/(<main id="main"[^>]*>)[\s\S]*?<\/main>/,(_,prefix)=>prefix+render(catalog,clock())+'</main>');
  // Every response evaluates the period. Neither a crawler nor a JS-disabled
  // visitor can receive yesterday's promotion from a shared edge cache.
  res.setHeader('Content-Type','text/html; charset=utf-8');res.setHeader('Cache-Control','no-store');
  return res.status(200).end(req.method==='HEAD'?'':html);
 };
}
module.exports={activeCampaigns,render,createHandler};
