const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function catalogDefaultOrder(brand){
 const rank=p=>brand?.primary_source&&p.kind==='purchase'?Number(!p.offers?.some(o=>o.id===p.id&&o.source===brand.primary_source)):0;
 return (a,b)=>Number(a.status==='soldout')-Number(b.status==='soldout')||rank(a)-rank(b);
}

export function isDiscounted(p){
  return p.release_status!=='coming_soon'&&p.kind==='purchase'&&(!!p.offers?.some(o=>['smartstore','imweb'].includes(o.source))||activePromotions(p).some(c=>c.type==='price_discount'))&&Number.isFinite(p.price)&&Number.isFinite(p.sale_price)&&p.price>0&&p.sale_price>=0&&p.sale_price<p.price;
}

export function activePromotions(p,now=Date.now()){
  if(p.release_status==='coming_soon'||p.kind!=='purchase'||!Array.isArray(p.promotions))return [];
  const zoned=v=>typeof v==='string'&&/(?:Z|[+-]\d{2}:\d{2})$/.test(v);
  return p.promotions.filter(c=>zoned(c.start_at)&&zoned(c.end_at)&&Number.isFinite(Date.parse(c.start_at))&&Number.isFinite(Date.parse(c.end_at))&&Date.parse(c.start_at)<=now&&now<Date.parse(c.end_at));
}

export function isPromotion(p){
  if(Array.isArray(p.promotions))return activePromotions(p).length>0;
  return p.release_status!=='coming_soon'&&p.kind==='purchase'&&Array.isArray(p.promotion_ids)&&p.promotion_ids.length>0;
}

export function isConsignmentUsed(p){
  return p.kind==='purchase'&&p.offers?.some(o=>o.source==='smartstore')&&/^\s*(?:\[(?:중고|위탁|위탁중고)\]|(?:중고|위탁중고)\s*[:：])/.test(p.name||'');
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

export function catalogSelection(data,{brand='',kind='purchase',cat='',type='',sale=false,benefit='all',collection=''}={}){
  const families=new Map(),members=new Map();
  for(const p of data.products){
    if((brand&&p.brand_id!==brand)||(kind!=='all'&&p.kind!==kind)||(sale&&!matchesBenefit(p,benefit))||(collection==='used'&&!isConsignmentUsed(p)))continue;
    const id=p.listing_id||p.id;if(!families.has(id)||p.id===id)families.set(id,p);
    if(!members.has(id))members.set(id,[]);members.get(id).push(p);
  }
  const base=[...families.values()];
  const preferred=kind==='purchase'?data.brands?.find(b=>b.id===brand)?.navigation_category_ids:null;
  if(kind==='purchase'&&data.brands?.find(b=>b.id===brand)?.exclusive_purchase_categories&&Array.isArray(preferred)&&cat&&!preferred.includes(cat))cat='';
  // Old bookmarked category URLs keep their original source tree and membership.
  const legacy=Array.isArray(preferred)&&!!cat&&!preferred.includes(cat);
  const navigation=Array.isArray(preferred)&&!legacy?new Set(preferred):null;
  const originalCategories=brand?data.categories.filter(c=>c.brand_id===brand&&(kind==='rental'?c.scope==='rental-brand':c.scope!=='rental-brand')&&(!navigation||navigation.has(c.id))):[];
  const brandInfo=data.brands?.find(b=>b.id===brand);
  const normalized=v=>String(v||'').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
  const aliases=[brandInfo?.name,brand,...(brandInfo?.aliases||[])].filter(Boolean).map(normalized);
  const repeatsBrand=c=>{let name=normalized(c.name);for(const alias of [...aliases].sort((a,b)=>b.length-a.length))name=name.split(alias).join('');return !name;};
  const parents=new Set(originalCategories.map(c=>c.parent_id));
  const wrappers=new Map(originalCategories.filter(c=>c.navigation_role==='wrapper'||(kind==='purchase'&&parents.has(c.id)&&repeatsBrand(c))).map(c=>[c.id,c]));
  const brandCategories=originalCategories.filter(c=>!wrappers.has(c.id)&&c.navigation_role!=='collection').map(c=>{
    let parent=c.parent_id;const seen=new Set();
    while(wrappers.has(parent)&&!seen.has(parent)){seen.add(parent);parent=wrappers.get(parent).parent_id}
    return parent===c.parent_id?c:{...c,parent_id:parent};
  });
  const typeCategories=data.categories.filter(c=>c.scope===(kind==='rental'?'rental-product':'product'));
  const categoryIds=p=>navigation?(p.navigation_category_ids??p.category_ids):p.category_ids;
  const matchesCategory=p=>!cat||categoryIds(p).includes(cat);
  const matchesType=p=>!type||p.type_ids.includes(type);
  const count=(field,filter)=>{const out=new Map();for(const family of members.values()){
    const ids=new Set(family.filter(filter).flatMap(p=>(field==='category_ids'?categoryIds(p):p[field])||[]));
    for(const id of ids)out.set(id,(out.get(id)||0)+1);
  }return out};
  return {base,brandCategories,typeCategories,selectedCategory:cat,
    typeFilteredCount:[...members.values()].filter(family=>family.some(matchesType)).length,
    brandCounts:count('category_ids',matchesType),
    typeCounts:count('type_ids',matchesCategory),
    rows:base.flatMap(p=>{const family=members.get(p.listing_id||p.id);const matching=family.filter(p=>matchesCategory(p)&&matchesType(p));return matching.length?[matching.includes(p)?p:matching[0]]:[]})};
}

export function productTypeNavigation(categories,counts,selected,href,{hideEmpty=false}={}){
  if(!categories.length)return '';
  const index=new Map(categories.map(c=>[c.id,c]));const current=index.get(selected);
  const activePath=new Set(categoryTrail(index,selected).map(c=>c.id));
  if(hideEmpty)categories=categories.filter(c=>counts.get(c.id)||activePath.has(c.id));
  const roots=categories.filter(c=>!c.parent_id);
  const link=c=>`<a href="${escape(href(c.id))}" class="${activePath.has(c.id)?'active':''}${!counts.get(c.id)?' is-empty':''}" ${c.id===selected?'aria-current="page"':''}>${escape(c.name)} <small>${counts.get(c.id)||0}</small></a>`;
  const children=current?categories.filter(c=>c.parent_id===current.id):[];
  const descendants=id=>{const rows=categories.filter(c=>c.parent_id===id);return rows.length?`<ul>${rows.map(c=>`<li>${link(c)}${descendants(c.id)}</li>`).join('')}</ul>`:''};
  const trail=current?`<div class="type-trail"><a href="${escape(href(null))}">제품 종류 전체</a>${categoryTrail(index,selected).map(c=>`<span aria-hidden="true">›</span>${c.id===selected?`<span aria-current="page">${escape(c.name)}</span>`:`<a href="${escape(href(c.id))}">${escape(c.name)}</a>`}`).join('')}</div>`:'';
  return `<section class="product-type-filter" aria-label="제품 종류별 카테고리"><div class="type-filter-heading"><h2>제품 종류</h2><span>브랜드와 함께 선택할 수 있습니다.</span></div><nav class="category-chips type-roots" aria-label="제품 대분류"><a href="${escape(href(null))}" ${!selected?'class="active" aria-current="page"':''}>전체</a>${roots.map(link).join('')}</nav>${trail}${current?categoryControls(children,current,href):''}<details class="product-types-all"><summary>세부 카테고리 전체 보기</summary><div class="type-directory">${roots.map(root=>`<section><h3>${link(root)}</h3>${descendants(root.id)}</section>`).join('')}</div></details></section>`;
}

export function productTypeBrandGroups(data,{kind='purchase',type='',sale=false,benefit='all',collection=''}={}){
 const scope=kind==='rental'?'rental-product':'product';
 const categories=data.categories.filter(c=>c.scope===scope);
 if(!categories.some(c=>c.id===type))return [];
 const children=categories.filter(c=>c.parent_id===type);
 const groups=new Map();
 for(const p of data.products){
  if((kind!=='all'&&p.kind!==kind)||!p.type_ids.includes(type)||(sale&&!matchesBenefit(p,benefit))||(collection==='used'&&!isConsignmentUsed(p)))continue;
  let group=groups.get(p.brand_id);
  if(!group){group={listings:new Set(),counts:new Map()};groups.set(p.brand_id,group)}
  const listing=p.listing_id||p.id;group.listings.add(listing);
  for(const child of children)if(p.type_ids.includes(child.id)){
   if(!group.counts.has(child.id))group.counts.set(child.id,new Set());
   group.counts.get(child.id).add(listing);
  }
 }
 return data.brands.filter(b=>groups.has(b.id)).map(brand=>({brand,count:groups.get(brand.id).listings.size,
  children:children.filter(c=>groups.get(brand.id).counts.has(c.id)).map(c=>({...c,count:groups.get(brand.id).counts.get(c.id).size}))}));
}

export function productTypeBrandNavigation(groups,current,selectedBrand,href){
 if(!current||!groups.length)return '';
 const label=brand=>{
  const korean=(brand.aliases||[]).find(v=>/^[가-힣]+$/.test(v));
  return korean&&!brand.name.includes(korean)?korean+' · '+brand.name:brand.name;
 };
 const card=group=>`<article class="type-brand-card${selectedBrand===group.brand.id?' active':''}"><h3><a href="${escape(href(group.brand.id,current.id))}" ${selectedBrand===group.brand.id?'aria-current="page"':''}>${escape(label(group.brand))}<small>${group.count.toLocaleString('ko-KR')}</small></a></h3>${group.children.length?`<nav aria-label="${escape(label(group.brand)+' '+current.name+' 세부 종류')}">${group.children.map(c=>`<a href="${escape(href(group.brand.id,c.id))}"><span>${escape(c.name)}</span><small>${c.count.toLocaleString('ko-KR')}</small></a>`).join('')}</nav>`:''}</article>`;
 return `<section class="type-brand-browser" aria-label="${escape(current.name+' 브랜드별 분류')}"><div class="type-filter-heading"><h2>${escape(current.name)} 브랜드별 보기</h2><span>${groups.length}개 브랜드</span></div><nav class="category-chips" aria-label="제품 종류의 브랜드 선택"><a href="${escape(href('',current.id))}" ${!selectedBrand?'class="active" aria-current="page"':''}>전체 브랜드</a>${groups.map(g=>`<a href="${escape(href(g.brand.id,current.id))}" ${selectedBrand===g.brand.id?'class="active" aria-current="page"':''}>${escape(label(g.brand))} <small>${g.count.toLocaleString('ko-KR')}</small></a>`).join('')}</nav><details class="type-brand-details" ${!selectedBrand&&groups.length<=12?'open':''}><summary>브랜드별 세부 종류 보기</summary><div class="type-brand-grid">${groups.map(card).join('')}</div></details></section>`;
}
