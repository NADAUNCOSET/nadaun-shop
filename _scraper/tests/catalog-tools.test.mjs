import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {categoryTrail,categoryControls,isDiscounted,isPromotion,matchesBenefit,benefitNavigation,catalogSelection,productTypeNavigation,brandSelectionHref} from '../../assets/shop/catalog-tools.js';
const map=new Map([{id:'a',name:'카메라',parent_id:null},{id:'b',name:'케이지',parent_id:'a'},{id:'c',name:'소니',parent_id:'b'}].map(c=>[c.id,c]));
test('deepest category keeps the parent link when there are no children',()=>{
 const trail=categoryTrail(map,'c');assert.deepEqual(trail.map(c=>c.id),['a','b','c']);
 const html=categoryControls([],map.get('c'),id=>'/brands/smallrig.html?cat='+encodeURIComponent(id||''));
 assert.ok(html.includes('← 상위 분류'));assert.ok(html.includes('href="/brands/smallrig.html?cat=b"'));
});
test('root category returns to all products and malformed cycles terminate',()=>{
 assert.ok(categoryControls([],map.get('a'),id=>id?'/cat/'+id:'/all').includes('href="/all"'));
 assert.equal(categoryControls([],null,()=>'/all'),'');
 const cyclic=new Map([['a',{id:'a',parent_id:'b'}],['b',{id:'b',parent_id:'a'}]]);assert.equal(categoryTrail(cyclic,'a').length,2);
});
test('discounts use our real public sale price, preserving rental and supplier distinctions',()=>{
 const p={kind:'purchase',price:10000,sale_price:8000,offers:[{source:'smartstore'}]};assert.equal(isDiscounted(p),true);
 for(const changed of [{kind:'rental'},{sale_price:10000},{sale_price:null},{sale_price:-1},{offers:[{source:'kpp'}]}])assert.equal(isDiscounted({...p,...changed}),false);
});
test('every imported leaf has an accessible route to its parent',()=>{
 const data=JSON.parse(fs.readFileSync('data/catalog/catalog.json','utf8'));const categories=new Map(data.categories.map(c=>[c.id,c]));
 const parents=new Set(data.categories.map(c=>c.parent_id));
 for(const c of data.categories.filter(c=>!parents.has(c.id))){
  const result=categoryControls([],c,id=>'/catalog.html?cat='+encodeURIComponent(id||''));
  assert.ok(result.includes('상위 분류'),c.id);assert.ok(result.includes(encodeURIComponent(c.parent_id||'')),c.id);
 }
 const discounted=data.products.filter(isDiscounted);assert.ok(discounted.length>0);
 console.log('Verified discounted products:',discounted.length);
});
test('promotion membership survives cross-store deduplication without inventing discounts',()=>{
 const data=JSON.parse(fs.readFileSync('data/catalog/catalog.json','utf8'));
 const source=JSON.parse(fs.readFileSync('data/catalog/sources/imweb-promotions.json','utf8'));
 const map=new Map(data.products.map(p=>[p.id,p]));
 for(const id of Object.keys(source.products)){
  const p=map.get(data.redirects[id]||id);assert.ok(p,id);assert.ok(isPromotion(p),id);
  assert.ok(matchesBenefit(p,'all'));assert.ok(matchesBenefit(p,'promotion'));
 }
 const p={kind:'purchase',price:10000,sale_price:10000,offers:[{source:'imweb'}],promotion_ids:['original-category']};
 assert.equal(isDiscounted(p),false);assert.ok(matchesBenefit(p));assert.equal(matchesBenefit(p,'discount'),false);
 assert.equal(isPromotion({...p,kind:'rental'}),false);
 const html=benefitNavigation('promotion',key=>'/catalog.html?sale=1&benefit='+key);
 assert.ok(html.includes('전체 혜택'));assert.ok(html.includes('할인상품'));assert.ok(html.includes('프로모션'));
});

test('brand and product-type filters combine while each facet counts the other selection',()=>{
 const product=(id,brand,kind,cat,type)=>({id,brand_id:brand,kind,category_ids:[cat],type_ids:[type]});
 const data={categories:[{id:'b1',brand_id:'sony',scope:'rental-brand'},{id:'b2',brand_id:'sony',scope:'rental-brand'},{id:'buy',brand_id:'sony',scope:'brand'},{id:'camera',scope:'rental-product'},{id:'mic',scope:'rental-product'}],products:[product('one','sony','rental','b1','camera'),product('two','sony','rental','b1','mic'),product('three','sony','rental','b2','camera'),product('purchase','sony','purchase','b1','camera'),product('other','canon','rental','b1','camera')]};
 const selected=catalogSelection(data,{brand:'sony',kind:'rental',cat:'b1',type:'camera'});
 assert.deepEqual(selected.rows.map(p=>p.id),['one']);assert.equal(selected.brandCounts.get('b1'),1);assert.equal(selected.brandCounts.get('b2'),1);assert.equal(selected.typeCounts.get('camera'),1);assert.equal(selected.typeCounts.get('mic'),1);
 assert.deepEqual(selected.brandCategories.map(c=>c.id),['b1','b2']);
 assert.deepEqual(catalogSelection(data,{kind:'rental',type:'camera'}).rows.map(p=>p.id),['one','three','other']);
});

test('real rental inventory and purchase listings stay separate without duplicate cards',()=>{
 const data=JSON.parse(fs.readFileSync('data/catalog/catalog.json','utf8'));
 for(const kind of ['rental','purchase']){
  const selection=catalogSelection(data,{kind});assert.ok(selection.rows.every(p=>p.kind===kind));
  assert.equal(selection.rows.length,new Set(data.products.filter(p=>p.kind===kind).map(p=>p.listing_id||p.id)).size);
  for(const c of selection.typeCategories)assert.equal(selection.typeCounts.get(c.id)||0,selection.rows.filter(p=>p.type_ids.includes(c.id)).length,c.id);
 }
 const rental=JSON.parse(fs.readFileSync('data/catalog/rental.json','utf8'));
 assert.deepEqual(catalogSelection(data,{kind:'rental'}).rows,catalogSelection(rental,{kind:'rental'}).rows);
 const sony=catalogSelection(rental,{kind:'rental',brand:'sony',type:'rent:11'});assert.ok(sony.rows.length);assert.ok(sony.rows.every(p=>p.brand_id==='sony'&&p.type_ids.includes('rent:11')));
});

test('full category directory includes deep leaves, empty TV group and a way back from every leaf',()=>{
 const data=JSON.parse(fs.readFileSync('data/catalog/rental.json','utf8'));const selection=catalogSelection(data,{kind:'rental'});
 const href=id=>'/catalog.html?kind=rental'+(id?'&type='+encodeURIComponent(id):'');
 const nav=productTypeNavigation(selection.typeCategories,selection.typeCounts,'rent:121',href);
 assert.ok(nav.includes('UHD TV'));assert.ok(nav.includes('TV·디스플레이'));
 assert.ok(nav.includes('href="/catalog.html?kind=rental&amp;type=rent%3A120">← 상위 분류'));
 for(const c of selection.typeCategories)assert.ok(nav.includes('type='+encodeURIComponent(c.id)),c.id);
});

test('brand switching preserves rental mode, product type and search but clears the old brand path',()=>{
 const url=new URL(brandSelectionHref('canon','?kind=rental&type=rent%3A24&cat=rental-brand%3Asony%3A24&page=8&q=카메라&available=1','rental'),'https://shop.nadaun.co');
 assert.equal(url.pathname,'/brands/canon.html');assert.equal(url.searchParams.get('kind'),'rental');assert.equal(url.searchParams.get('type'),'rent:24');assert.equal(url.searchParams.get('q'),'카메라');assert.equal(url.searchParams.get('available'),'1');assert.equal(url.searchParams.has('cat'),false);assert.equal(url.searchParams.has('page'),false);
 assert.equal(new URL(brandSelectionHref('',url.search,'rental'),url.origin).pathname,'/catalog.html');
});
