const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const imageUrl=value=>{try{const u=new URL(value,'https://shop.nadaun.co');return ['http:','https:'].includes(u.protocol)?escape(value):''}catch{return ''}};

export function browseDirectoryHtml(data,kind){
 if(!['purchase','rental'].includes(kind))return '';
 const entries=data.category_gallery?.[kind]||[];
 const title=kind==='rental'?'렌탈 장비 종류':'제품 종류';
 const rows=data.products.filter(p=>p.kind===kind);
 const brands=data.brands.filter(b=>rows.some(p=>p.brand_id===b.id));
 const categoryTiles=entries.map(e=>`<a class="category-image-tile" href="${escape(e.href)}"><span class="category-image"><img src="${imageUrl(e.image)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer"></span><strong>${escape(e.name)}</strong></a>`).join('');
 const brandTiles=brands.map(b=>{
  const members=rows.filter(p=>p.brand_id===b.id),photo=members.find(p=>p.id===b.representative_id)||members.find(p=>p.status!=='soldout')||members[0];
  const mark=b.image_kind==='logo'&&!b.logo_dark?`<span class="brand-mark"><img src="${imageUrl(b.logo)}" alt="${escape(b.name)}" loading="lazy"></span>`:`<span class="brand-mark brand-mark-text">${escape(b.name)}</span>`;
  return `<a class="brand-tile" href="/brands/${encodeURIComponent(b.id)}.html?kind=${kind}" target="_blank" rel="noopener" aria-label="${escape(b.name)} ${kind==='rental'?'렌탈':'구매'} 상품 새 창">${mark}<span class="brand-visual brand-object"><img src="${imageUrl(photo.image)}" alt="${escape(photo.name)}" loading="lazy" decoding="async" referrerpolicy="no-referrer"></span></a>`;
 }).join('');
 return `<div class="browse-directory"><nav class="browse-kinds" aria-label="쇼핑 목적"><a href="/catalog.html?kind=purchase" ${kind==='purchase'?'aria-current="page"':''}>제품 구매</a><a href="/catalog.html?kind=rental" ${kind==='rental'?'aria-current="page"':''}>제품 렌탈</a><a href="/gifts.html">기프트 구매</a></nav><section class="category-gallery" aria-label="${title}"><div class="section-head"><div><h2>${title}로 찾기</h2><p>종류를 고르면 모든 브랜드의 해당 상품을 볼 수 있습니다.</p></div><a class="text-button" href="#catalog-products">상품 바로 보기 ↓</a></div><nav class="category-image-grid" aria-label="${title} 선택">${categoryTiles}</nav></section><section class="browse-brands" aria-label="브랜드별 보기"><div class="section-head"><div><h2>브랜드로 찾기</h2><p>알고 있는 브랜드가 있다면 바로 선택하세요.</p></div></div><div class="brand-grid">${brandTiles}</div></section></div>`;
}
