const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const handler=require('../../api/product.js');
const catalog=JSON.parse(fs.readFileSync('data/catalog/catalog.json','utf8'));
function request(url,method='GET'){
 const result={headers:{},status:200,body:''};
 handler({url,method},{setHeader(k,v){result.headers[k]=v},status(s){result.status=s;return this},end(s=''){result.body=s;return this}});return result;
}
test('server renders unique product metadata, semantic content and schema without JavaScript',()=>{
 const p=catalog.products.find(p=>p.brand_id==='dji');const r=request('/item.html?id='+p.id);
 assert.equal(r.status,200);assert.match(r.headers['Content-Type'],/text\/html/);
 assert.match(r.body,/<h1>[^<]+<\/h1>/);assert.ok(r.body.includes('https://shop.nadaun.co/item.html?id='+p.id));
 const schemas=[...r.body.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map(m=>JSON.parse(m[1]));
 const product=schemas.find(s=>s['@type']==='Product');assert.equal(product.name,p.name);assert.equal(product.sku,p.id);assert.equal(product.offers,undefined);
 assert.match(r.body,/content="index,follow,max-image-preview:large"/);assert.ok(!r.body.includes('{{'));
});
test('every product serves canonical metadata with descriptions limited to 80 characters',()=>{
 for(const p of catalog.products){
  const r=request('/item.html?id='+p.id);assert.equal(r.status,200);
  const desc=r.body.match(/<meta name="description" content="([^"]*)"/)[1].replace(/&(amp|lt|gt|quot|#39);/g,'x');
  assert.ok(desc.length>0&&desc.length<=80,p.id);
  assert.ok(r.body.includes('https://shop.nadaun.co/item.html?id='+p.id));
 }
});
test('old duplicates redirect permanently and missing products return a real 404',()=>{
 const [old,id]=Object.entries(catalog.redirects)[0];const r=request('/item.html?id='+old);
 assert.equal(r.status,308);assert.equal(r.headers.Location,'/item.html?id='+id);
 for(const value of ['','missing','../../.env','<script>alert(1)</script>']){
  const r=request('/item.html?id='+encodeURIComponent(value));assert.equal(r.status,404);assert.equal(r.headers['X-Robots-Tag'],'noindex');assert.ok(!r.body.includes(value)||!value);
 }
});
test('HEAD does not send a body and write methods are rejected',()=>{
 assert.equal(request('/item.html?id='+catalog.products[0].id,'HEAD').body,'');
 assert.equal(request('/item.html?id='+catalog.products[0].id,'POST').status,405);
});
