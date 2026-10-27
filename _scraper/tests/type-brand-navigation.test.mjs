import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {productTypeBrandGroups,productTypeBrandNavigation,brandSelectionHref,catalogSelection} from '../../assets/shop/catalog-tools.js';

test('camera manufacturers exclude compatible accessory makers and keep family counts unique',()=>{
 const categories=[{id:'camera',name:'카메라',scope:'product'},
  {id:'mirrorless',name:'미러리스',parent_id:'camera',scope:'product'},
  {id:'compact',name:'컴팩트',parent_id:'camera',scope:'product'}];
 const product=(id,brand_id,type_ids,extra={})=>({id,brand_id,type_ids,kind:'purchase',category_ids:[],...extra});
 const data={categories,brands:[{id:'sony',name:'SONY',aliases:['소니']},{id:'ricoh',name:'RICOH'},{id:'smallrig',name:'SmallRig'}],products:[
  product('s1','sony',['camera','mirrorless']),product('s2','sony',['camera','mirrorless'],{listing_id:'s1'}),
  product('r1','ricoh',['camera','compact']),product('cage-for-sony','smallrig',['rig']),
  product('rent','sony',['camera','mirrorless'],{kind:'rental'})]};
 const groups=productTypeBrandGroups(data,{type:'camera'});
 assert.deepEqual(groups.map(g=>[g.brand.id,g.count,g.children.map(c=>[c.id,c.count])]),[['sony',1,[['mirrorless',1]]],['ricoh',1,[['compact',1]]]]);
 assert.equal(productTypeBrandGroups(data,{type:'camera',kind:'rental'}).length,0);
 const html=productTypeBrandNavigation(groups,categories[0],'sony',(brand,type)=>brandSelectionHref(brand,'?type='+type,'purchase'));
 assert.ok(html.includes('카메라 브랜드별 보기'));assert.ok(html.includes('소니 · SONY'));
 assert.ok(html.includes('/brands/sony.html?type=mirrorless&amp;kind=purchase'));
 assert.ok(!html.includes('SmallRig'));assert.ok(!html.includes('>컴팩트</span><small>0'));
});

test('each published type-to-brand link selects the same manufacturer and type without losing listings',()=>{
 const data=JSON.parse(fs.readFileSync('data/catalog/catalog.json','utf8'));
 for(const type of ['type:camera','type:kpp:03','type:kpp:07','type:power']){
  const groups=productTypeBrandGroups(data,{type});
  const expected=new Map();
  for(const p of data.products.filter(p=>p.kind==='purchase'&&p.type_ids.includes(type))){
   if(!expected.has(p.brand_id))expected.set(p.brand_id,new Set());expected.get(p.brand_id).add(p.listing_id||p.id);
  }
  assert.deepEqual(new Map(groups.map(g=>[g.brand.id,g.count])),new Map([...expected].map(([b,ids])=>[b,ids.size])));
  for(const group of groups){
   const q=new URLSearchParams({type,cat:'old-brand-category',page:'4',kind:'purchase'});
   const url=new URL(brandSelectionHref(group.brand.id,q,'purchase'),'https://shop.nadaun.co');
   assert.equal(url.searchParams.get('type'),type);assert.equal(url.searchParams.has('cat'),false);assert.equal(url.searchParams.has('page'),false);
   const rows=catalogSelection(data,{brand:group.brand.id,type}).rows;
   assert.ok(rows.every(p=>p.brand_id===group.brand.id&&p.type_ids.includes(type)));
  }
 }
});

test('a non-default mount variant remains reachable from the exact type and source category',()=>{
 const data={brands:[{id:'lens-maker'}],categories:[{id:'lens',scope:'product'},{id:'mount-z',scope:'product',parent_id:'lens'},{id:'mount-e',scope:'product',parent_id:'lens'},{id:'source-e',brand_id:'lens-maker'},{id:'source-z',brand_id:'lens-maker'}],products:[
  {id:'e',listing_id:'e',brand_id:'lens-maker',kind:'purchase',type_ids:['lens','mount-e'],category_ids:['source-e']},
  {id:'z',listing_id:'e',brand_id:'lens-maker',kind:'purchase',type_ids:['lens','mount-z'],category_ids:['source-z']} ]};
 const view=catalogSelection(data,{brand:'lens-maker',type:'mount-z',cat:'source-z'});
 assert.deepEqual(view.rows.map(p=>p.id),['z']);assert.equal(view.brandCounts.get('source-z'),1);assert.equal(view.typeCounts.get('mount-z'),1);
 assert.equal(catalogSelection(data,{brand:'lens-maker',type:'mount-z',cat:'source-e'}).rows.length,0);
 const groups=productTypeBrandGroups(data,{type:'lens'});assert.equal(groups[0].count,1);assert.equal(groups[0].children.length,2);
});
