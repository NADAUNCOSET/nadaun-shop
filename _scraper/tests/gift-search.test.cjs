const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const gift=require('../../server/gift-catalog.cjs');
const search=require('../../server/shop-search.cjs');

test('all gift IDs have counted categories and exact detail buckets without private data',()=>{
 assert.equal(gift.products.size,gift.data.meta.product_count);
 const counts=new Map();let verified=0;
 for(const p of gift.data.products){
  assert.match(p.id,/^[1-9]\d+$/);
  assert.deepEqual(Object.keys(p).sort(),['category_ids','detail_available','id','image','name','soldout']);
  for(const id of p.category_ids){assert(gift.categories.has(id));counts.set(id,(counts.get(id)||0)+1);}
  if(p.detail_available)verified++;
 }
 for(const c of gift.data.categories){assert.equal(c.count,counts.get(c.id));assert(gift.products.get(c.product_id).category_ids.includes(c.id));}
 assert.equal(verified,gift.data.meta.detail_count);
 let count=0;
 for(let n=0;n<256;n++){
  const bucket=JSON.parse(fs.readFileSync(`data/gift/details/${n.toString(16).padStart(2,'0')}.json`));
  for(const [id,d] of Object.entries(bucket)){assert.equal(Number(id)%256,n);assert(gift.products.get(id).detail_available);assert.equal(d.id,id);assert.deepEqual(Object.keys(d).sort(),['choices','id','images','minimum_quantity','specifications']);count++;}
 }
 assert.equal(count,verified);
});

test('gift browsing is internal, paginated and keeps the upward path at the last category',()=>{
 const home=gift.directory(new URLSearchParams());assert.equal(home.status,200);
 assert.equal((home.body.match(/class="category-image-tile"/g)||[]).length,12);
 assert.equal((home.body.match(/class="product-card /g)||[]).length,48);
 assert(!home.body.includes('nadaun-gift.com'));
 assert(!home.body.includes('brand-grid'));
 const leaf=gift.data.categories.find(c=>c.parent_ids.length);
 const page=gift.directory(new URLSearchParams({category:leaf.id}));
 assert(page.rows.every(p=>p.category_ids.includes(leaf.id)));
 assert(page.body.includes(`class="gift-back" href="/gifts.html?category=${leaf.parent_ids[0]}`));
 assert.equal(gift.directory(new URLSearchParams({category:'missing'})).status,404);
 assert.equal(gift.directory(new URLSearchParams({page:'999999'})).status,404);
 const second=gift.directory(new URLSearchParams({page:'2'}));assert.equal(second.page,2);
});

test('detail identity and query escaping work for both verified and pending details',()=>{
 for(const verified of [true,false]){
  const p=gift.data.products.find(x=>x.detail_available===verified),d=gift.detail(p.id);
  assert.equal(d.status,200);assert.equal(d.schema.sku,p.id);assert(d.body.includes(gift.esc(p.name)));
  assert(!d.schema.offers);assert(!d.body.includes('nadaun-gift.com'));
 }
 assert.equal(gift.detail('../suppliers').status,404);
 const q='<script>alert(1)</script>',r=search.render(new URLSearchParams({q}));
 assert(!r.body.includes(q));assert(r.body.includes('&lt;script&gt;'));assert(r.noindex);
});

test('unified search returns purchase, rental and gifts and isolates scope',()=>{
 for(const [q,kind] of [['DJI','purchase'],['SONY','rental'],['텀블러','gift']]){
  const rows=search.results(q);assert(rows.some(p=>p.search_kind===kind),q);
  const result=search.render(new URLSearchParams({q,scope:kind}));assert(result.counts[kind]>0);
 }
 const id=gift.data.products[0].id;assert.equal(search.results(id)[0].id,id);
 assert.equal(search.results('타월').filter(p=>p.search_kind==='gift').length,search.results('타올').filter(p=>p.search_kind==='gift').length);
});

test('SSR handlers deliver HTML, metadata, HEAD, 404 and method restrictions',()=>{
 for(const [modulePath,url,expected] of [
  ['../../api/gifts.js','/gifts.html',200],
  ['../../api/gift-product.js','/gift-item.html?id='+gift.data.products[0].id,200],
  ['../../api/search.js','/search.html?q=텀블러',200],
  ['../../api/gift-product.js','/gift-item.html?id=not-found',404]]){
  const handle=require(modulePath);
  for(const method of ['GET','HEAD','POST']){
   const res={headers:{},setHeader(k,v){this.headers[k]=v;},status(s){this.code=s;return this;},end(body=''){this.body=body;return this;}};
   handle({method,url},res);assert.equal(res.code,method==='POST'?405:expected);
   if(method!=='GET'){assert.equal(res.body,'');continue;}
   assert(res.body.includes('<h1>'));assert(res.body.includes('action="/search.html"'));
   for(const pattern of [/<meta name="description" content="([^"]*)"/,/<meta property="og:description" content="([^"]*)"/])assert(res.body.match(pattern)?.[1].length<=100);
   if(expected===404)assert.equal(res.headers['X-Robots-Tag'],'noindex');
  }
 }
});
