import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {categoryTrail,categoryControls,isDiscounted} from '../../assets/shop/catalog-tools.js';
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
