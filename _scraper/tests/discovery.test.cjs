const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const catalog=JSON.parse(fs.readFileSync('data/catalog/catalog.json','utf8'));
const handler=require('../../api/product.js');
const normalize=v=>v.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g,'');

test('all products have bounded relevant tags, working tag searches and the correct rental or purchase description',()=>{
 for(const p of catalog.products){
  const d=p.discovery;
  assert.ok(d.tags.length>=2&&d.tags.length<=7,p.id);
  assert.ok(d.description.length>0&&d.description.length<=80,p.id);
  assert.match(d.description,p.kind==='rental'?/렌탈·대여 안내/:/구매 안내/);
  const searchable=normalize([p.name,...d.search_terms].join(' '));
  for(const tag of d.tags)assert.ok(tag.split(/\s+/).every(word=>searchable.includes(normalize(word))),p.id+': '+tag);
  assert.ok(!d.tags.some(tag=>/collective|협찬|촬영제작/i.test(tag)),p.id);
 }
 const nd=catalog.products.find(p=>/\bND64\b/.test(p.name));
 assert.ok(nd&&nd.discovery.search_terms.includes('엔디필터'));
 const wandrd=catalog.products.filter(p=>p.brand_id==='wandrd'&&!/필터|\bND\d*\b/i.test(p.name));
 assert.ok(wandrd.length);
 assert.ok(wandrd.every(p=>!p.discovery.tags.includes('ND필터')));
});

test('rental server content and structured product terms are visible and consistent',()=>{
 const p=catalog.products.find(p=>p.kind==='rental');let body='';
 handler({url:'/item.html?id='+p.id,method:'GET'},{setHeader(){},status(){return this},end(v){body=v;return this}});
 assert.match(body,/렌탈·대여 안내/);
 assert.match(body,/aria-label="관련 상품 검색"/);
 const schemas=[...body.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map(m=>JSON.parse(m[1]));
 assert.equal(schemas.find(s=>s['@type']==='Product').keywords,p.discovery.tags.join(', '));
 assert.ok(!body.includes('NADAUN COLLECTIVE'));
});

test('service relationships have visible explanations and a discoverable guide link',()=>{
 const page=fs.readFileSync('services.html','utf8');
 assert.match(page,/data-mode="guide"/);
 for(const anchor of ['purchase','rental','collaboration','production'])assert.ok(page.includes('id="'+anchor+'"'));
 assert.match(page,/href="https:\/\/collective.nadaun.co\/"/);
 assert.match(page,/나다운의 제작 서비스인 NADAUN COLLECTIVE/);
 assert.match(page,/"subOrganization"/);
 assert.ok(!page.includes('"sameAs"'));
 assert.match(fs.readFileSync('index.html','utf8'),/href="\/services.html"/);
});

test('company and four customer information pages are crawlable and linked from the shared footer',()=>{
 const pages=['about.html','terms.html','privacy.html','services.html','shipping.html'];
 for(const file of pages){
  const html=fs.readFileSync(file,'utf8');assert.match(html,/<h1>/);assert.doesNotMatch(html,/\{\{/);
  for(const link of pages)assert.ok(html.includes('href="/'+link+'"'),file+' → '+link);
  assert.ok(html.includes('https://shop.nadaun.co/'+file));
 }
 assert.match(fs.readFileSync('about.html','utf8'),/data-mode="about"/);
 assert.ok(fs.readFileSync('catalog-sitemap.xml','utf8').includes('https://shop.nadaun.co/about.html'));
});

test('each canonical product has its real image in the sitemap, without duplicate or checkout URLs',()=>{
 const xml=fs.readFileSync('catalog-sitemap.xml','utf8');
 assert.match(xml,/xmlns:image="http:\/\/www.google.com\/schemas\/sitemap-image\/1.1"/);
 const entries=[...xml.matchAll(/<url>(.*?)<\/url>/g)].map(m=>m[1]);
 assert.equal(entries.filter(e=>e.includes('<image:image>')).length,catalog.products.length);
 const urls=entries.map(e=>e.match(/<loc>(.*?)<\/loc>/)[1]);
 assert.equal(new Set(urls).size,urls.length);
 assert.ok(urls.includes('https://shop.nadaun.co/services.html'));
 assert.ok(!urls.some(u=>/checkout|cart\.html/.test(u)));
 for(const old of Object.keys(catalog.redirects))assert.ok(!urls.includes('https://shop.nadaun.co/item.html?id='+old));
});
