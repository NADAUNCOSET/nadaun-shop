const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function isDiscounted(p){
  return p.kind==='purchase'&&!!p.offers?.some(o=>['smartstore','imweb'].includes(o.source))&&Number.isFinite(p.price)&&Number.isFinite(p.sale_price)&&p.price>0&&p.sale_price>=0&&p.sale_price<p.price;
}

export function isPromotion(p){
  return p.kind==='purchase'&&Array.isArray(p.promotion_ids)&&p.promotion_ids.length>0;
}

export function matchesBenefit(p,mode='all'){
  return mode==='discount'?isDiscounted(p):mode==='promotion'?isPromotion(p):isDiscounted(p)||isPromotion(p);
}

export function benefitNavigation(active,href){
  return `<nav class="category-chips benefit-tabs" aria-label="할인·프로모션 분류">${[['all','전체 혜택'],['discount','할인상품'],['promotion','프로모션']].map(([key,label])=>`<a href="${escape(href(key))}" ${active===key?'aria-current="page" class="active"':''}>${label}</a>`).join('')}</nav>`;
}

export function categoryTrail(categories,id){
  const path=[],seen=new Set();let current=categories.get(id);
  while(current&&!seen.has(current.id)){path.unshift(current);seen.add(current.id);current=categories.get(current.parent_id)}
  return path;
}

export function categoryControls(children,selected,href){
  if(!selected&&!children.length)return '';
  const parent=selected?`<a class="category-parent" href="${escape(href(selected.parent_id||null))}">← 상위 분류</a>`:'';
  return `<nav class="category-chips" aria-label="카테고리 이동">${parent}${children.map(c=>`<a href="${escape(href(c.id))}">${escape(c.name)}</a>`).join('')}</nav>`;
}

export function brandSelectionHref(brand,search,kind){
  const q=new URLSearchParams(search);
  for(const key of ['brand','cat','page'])q.delete(key);
  q.set('kind',kind);
  return (brand?`/brands/${encodeURIComponent(brand)}.html`:'/catalog.html')+'?'+q.toString();
}

export function catalogSelection(data,{brand='',kind='purchase',cat='',type='',sale=false,benefit='all'}={}){
  const families=new Map();
  for(const p of data.products){
    if((brand&&p.brand_id!==brand)||(kind!=='all'&&p.kind!==kind)||(sale&&!matchesBenefit(p,benefit)))continue;
    const id=p.listing_id||p.id;if(!families.has(id)||p.id===id)families.set(id,p);
  }
  const base=[...families.values()];
  const brandCategories=brand?data.categories.filter(c=>c.brand_id===brand&&(kind==='rental'?c.scope==='rental-brand':c.scope!=='rental-brand')):[];
  const typeCategories=data.categories.filter(c=>c.scope===(kind==='rental'?'rental-product':'product'));
  const count=(rows,field)=>{const out=new Map();for(const p of rows)for(const id of new Set(p[field]||[]))out.set(id,(out.get(id)||0)+1);return out};
  return {base,brandCategories,typeCategories,
    brandCounts:count(base.filter(p=>!type||p.type_ids.includes(type)),'category_ids'),
    typeCounts:count(base.filter(p=>!cat||p.category_ids.includes(cat)),'type_ids'),
    rows:base.filter(p=>(!cat||p.category_ids.includes(cat))&&(!type||p.type_ids.includes(type)))};
}

export function productTypeNavigation(categories,counts,selected,href){
  if(!categories.length)return '';
  const roots=categories.filter(c=>!c.parent_id);
  const index=new Map(categories.map(c=>[c.id,c]));const current=index.get(selected);
  const activePath=new Set(categoryTrail(index,selected).map(c=>c.id));
  const link=c=>`<a href="${escape(href(c.id))}" class="${activePath.has(c.id)?'active':''}${!counts.get(c.id)?' is-empty':''}" ${c.id===selected?'aria-current="page"':''}>${escape(c.name)} <small>${counts.get(c.id)||0}</small></a>`;
  const children=current?categories.filter(c=>c.parent_id===current.id):[];
  const descendants=id=>{const rows=categories.filter(c=>c.parent_id===id);return rows.length?`<ul>${rows.map(c=>`<li>${link(c)}${descendants(c.id)}</li>`).join('')}</ul>`:''};
  const trail=current?`<div class="type-trail"><a href="${escape(href(null))}">제품 종류 전체</a>${categoryTrail(index,selected).map(c=>`<span aria-hidden="true">›</span>${c.id===selected?`<span aria-current="page">${escape(c.name)}</span>`:`<a href="${escape(href(c.id))}">${escape(c.name)}</a>`}`).join('')}</div>`:'';
  return `<section class="product-type-filter" aria-label="제품 종류별 카테고리"><div class="type-filter-heading"><h2>제품 종류</h2><span>브랜드와 함께 선택할 수 있습니다.</span></div><nav class="category-chips type-roots" aria-label="제품 대분류"><a href="${escape(href(null))}" ${!selected?'class="active" aria-current="page"':''}>전체</a>${roots.map(link).join('')}</nav>${trail}${current?categoryControls(children,current,href):''}<details class="product-types-all"><summary>세부 카테고리 전체 보기</summary><div class="type-directory">${roots.map(root=>`<section><h3>${link(root)}</h3>${descendants(root.id)}</section>`).join('')}</div></details></section>`;
}
