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
