import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const {browseDirectoryHtml}=await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync('assets/shop/browse.js','utf8')).toString('base64'));
const data=JSON.parse(fs.readFileSync('data/catalog/catalog.json','utf8'));

test('every image category links to its real product kind and actual membership',()=>{
 for(const kind of ['purchase','rental']){
  const entries=data.category_gallery[kind];assert.ok(entries.length>=10);assert.equal(new Set(entries.map(e=>e.id)).size,entries.length);
  for(const e of entries){const p=data.products.find(p=>p.id===e.product_id);assert.equal(p.kind,kind);assert.ok(p.type_ids.includes(e.id));assert.equal(e.image,p.image);const u=new URL(e.href,'https://shop.nadaun.co');assert.equal(u.searchParams.get('kind'),kind);assert.equal(u.searchParams.get('type'),e.id)}
 }
});
test('purpose, image types and brands appear in order, with kind preserved in brand links',()=>{
 for(const kind of ['purchase','rental']){const html=browseDirectoryHtml(data,kind);assert.ok(html.indexOf('browse-kinds')<html.indexOf('category-gallery'));assert.ok(html.indexOf('category-gallery')<html.indexOf('browse-brands'));assert.ok(html.includes('.html?kind='+kind));assert.doesNotMatch(html,/undefined|javascript:/)}
 assert.equal(browseDirectoryHtml(data,'gift'),'');
});
test('home places image categories before brands, rental best before purchase cards',()=>{
 const html=fs.readFileSync('index.html','utf8');assert.ok(html.indexOf('shop-departments')<html.indexOf('category-image-grid'));assert.ok(html.indexOf('category-image-grid')<html.indexOf('id="brands"'));assert.ok(html.indexOf('data-scene="rental"')<html.indexOf('data-scene="purchase"'));
});
