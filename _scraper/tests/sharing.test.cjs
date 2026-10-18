const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {socialMetadata,shareImageURL}=require('../../server/share-metadata.cjs');
const {MAX_BYTES,allowedRemote,fetchImage,createImageHandler}=require('../../server/share-image.cjs');
const catalog=JSON.parse(fs.readFileSync('data/catalog/catalog.json'));
const gifts=JSON.parse(fs.readFileSync('data/gift/catalog.json'));
const productHandler=require('../../api/product.js');
const giftHandler=require('../../api/gift-product.js');
const JPEG=Buffer.from([255,216,255,224,0,16,74,70,73,70,0,0]);
function response(){return {headers:{},code:200,body:'',setHeader(k,v){this.headers[k]=v;return this;},status(code){this.code=code;return this;},end(body=''){this.body=body;return this;}};}
function meta(html,key){const match=html.match(new RegExp('<meta (?:name|property)="'+key+'" content="([^"]*)"'));return match?.[1].replace(/&amp;/g,'&').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>');}
function invoke(handler,url,method='GET'){const res=response();handler({url,method},res);return res;}

test('purchase, rental and gift HTML expose the exact product image, canonical identity and full social metadata before JavaScript',()=>{
 const samples=[...new Map(catalog.products.map(p=>[p.kind,p])).values()];
 samples.push(...[true,false].map(detail=>gifts.products.find(p=>p.detail_available===detail)));
 for(const p of samples){
  const kind=p.kind?'product':'gift',url=`/${kind==='gift'?'gift-item':'item'}.html?id=${p.id}`;
  const {body,code}=invoke(kind==='gift'?giftHandler:productHandler,url);assert.equal(code,200);
  const image=meta(body,'og:image');assert.equal(image,shareImageURL(kind,p));
  assert.equal(meta(body,'twitter:image'),image);assert.equal(meta(body,'og:image:secure_url'),image);
  assert.equal(meta(body,'og:image:width'),'1200');assert.equal(meta(body,'og:image:height'),'630');assert.equal(meta(body,'og:image:type'),'image/jpeg');
  assert.equal(meta(body,'og:image:alt'),p.name);assert.equal(meta(body,'twitter:card'),'summary_large_image');
  assert.equal(meta(body,'og:title'),meta(body,'twitter:title'));assert.ok(meta(body,'og:title').includes(p.name));
  assert.equal(meta(body,'og:description'),meta(body,'twitter:description'));assert.ok(meta(body,'og:description').length<=80);
  assert.equal(meta(body,'og:url'),'https://shop.nadaun.co'+url);
  assert.equal((body.match(/property="og:image"/g)||[]).length,1);
 }
 const namedRental=catalog.products.find(p=>p.kind==='rental'&&/렌탈$/.test(p.name));
 if(namedRental)assert.ok(!meta(invoke(productHandler,'/item.html?id='+namedRental.id).body,'og:title').includes('렌탈 렌탈'));
 assert.equal(invoke(productHandler,'/item.html?id=constructor').code,404);
});

test('every published equipment and gift item receives a distinct valid canonical share-image URL and an approved source',()=>{
 const seen=new Set();
 for(const [kind,rows] of [['product',catalog.products],['gift',gifts.products]])for(const p of rows){
  const url=new URL(shareImageURL(kind,p));assert.equal(url.origin,'https://shop.nadaun.co');assert.equal(url.pathname,'/share-image.jpg');
  assert.equal(url.searchParams.get('id'),p.id);assert.equal(url.searchParams.get('kind'),kind);assert.match(url.searchParams.get('v'),/^[a-f0-9]{16}$/);
  assert.ok(!seen.has(url.href),p.id);seen.add(url.href);
  const image=new URL(p.image,'https://shop.nadaun.co');
  const local=image.origin==='https://shop.nadaun.co'&&image.pathname.startsWith('/assets/');
  assert.ok(allowedRemote(p.image)||local,p.id+': '+p.image);
  if(local)assert.ok(fs.existsSync('.'+image.pathname),'Missing local share source '+p.id);
 }
});

test('metadata replacement escapes hostile text, drops conflicting inherited tags and versions changed images',()=>{
 const html=socialMetadata('<html><head><title>old</title><meta property="og:image" content="logo"><meta property="og:image:width" content="20"><meta name="twitter:card" content="summary"><link rel="canonical" href="old"></head></html>',{title:'A "camera" <script>',description:'a & b',canonical:'https://shop.nadaun.co/item.html?id=1',image:'https://shop.nadaun.co/share-image.jpg?id=1&kind=product',imageAlt:'a & b',width:1200,height:630});
 assert.ok(!html.includes('<script>'));assert.equal(meta(html,'og:title'),'A "camera" <script>');assert.equal(meta(html,'og:image:width'),'1200');assert.equal((html.match(/rel="canonical"/g)||[]).length,1);
 assert.notEqual(shareImageURL('product',{id:'x',image:'https://kppkpp.co.kr/a.jpg'}),shareImageURL('product',{id:'x',image:'https://kppkpp.co.kr/b.jpg'}));
});

test('image fetch accepts real JPEG bytes with a generic source MIME but rejects private/unapproved redirects, HTML and excessive bodies',async()=>{
 for(const url of ['https://127.0.0.1/a.jpg','https://localhost/a','http://169.254.169.254/a','file:///tmp/a','https://kppkpp.co.kr.evil.test/a','https://user:pass@kppkpp.co.kr/a','https://kppkpp.co.kr:444/a'])assert.equal(allowedRemote(url),null,url);
 const data=await fetchImage('https://cloudfront.imggift.com/a.jpg',async()=>new Response(JPEG,{headers:{'Content-Type':'binary/octet-stream'}}));assert.deepEqual(data,JPEG);
 let called=0;await assert.rejects(fetchImage('https://kppkpp.co.kr/a',async()=>{called++;return new Response(null,{status:302,headers:{Location:'http://127.0.0.1/private'}})}),/unapproved_image_redirect/);assert.equal(called,1);
 await assert.rejects(fetchImage('https://kppkpp.co.kr/a',async()=>new Response('<html>not an image</html>')),/invalid_image_bytes/);
 await assert.rejects(fetchImage('https://kppkpp.co.kr/a',async()=>new Response(JPEG,{headers:{'Content-Length':MAX_BYTES+1}})),/image_too_large/);
 await assert.rejects(fetchImage('https://kppkpp.co.kr/a',async()=>new Response(Buffer.alloc(MAX_BYTES+1))),/image_too_large/);
});

test('public image endpoint validates IDs, bounds source fetches and returns a labeled cached fallback for denied media',async()=>{
 let reads=0;const handler=createImageHandler({productFor:(kind,id)=>id==='ok'?{id,image:'https://kppkpp.co.kr/a.jpg'}:null,fetchImpl:async()=>{reads++;return new Response(null,{status:403})},render:async b=>b,fallback:()=>JPEG});
 for(const url of ['/share-image.jpg?url=https://localhost','/share-image.jpg?kind=product&id=missing','/share-image.jpg?kind=gift&id=../../secret']){const r=response();await handler({url,method:'GET'},r);assert.equal(r.code,404);}
 assert.equal(reads,0);
 for(const method of ['GET','HEAD']){const r=response();await handler({url:'/share-image.jpg?kind=product&id=ok',method},r);assert.equal(r.code,200);assert.equal(r.headers['Content-Type'],'image/jpeg');assert.equal(r.headers['X-Nadaun-Share-Image'],'fallback');assert.match(r.headers['Cache-Control'],/s-maxage=21600/);assert.equal(method==='HEAD'?r.body.length:r.body.compare(JPEG),0);}
 assert.equal(reads,1,'access denial must not be retried');
 const r=response();await handler({url:'/share-image.jpg?kind=product&id=ok',method:'POST'},r);assert.equal(r.code,405);
});

test('rendering emits one decodable JPEG at 1200x630 for a real local PNG',async()=>{
 const sharp=require('sharp'),{jpeg}=require('../../server/share-image.cjs');
 const bytes=await jpeg(fs.readFileSync('assets/shop/nadaun-logo.png'));
 const metadata=await sharp(bytes).metadata();assert.equal(metadata.format,'jpeg');assert.equal(metadata.width,1200);assert.equal(metadata.height,630);assert.ok(bytes.length<1024*1024);
});

test('client hydration preserves the initial social image rather than replacing it with the third-party thumbnail',()=>{
 const code=fs.readFileSync('assets/shop/shop.js','utf8');assert.ok(!code.includes('document.querySelector(\'meta[property="og:image"]\').content=new URL(p.image'));
 assert.ok(code.includes("' | 나다운 스페이스'"));
});

 test('new supplier originals render as real product previews and ship with the image function',async()=>{
  const sharp=require('sharp'),config=JSON.parse(fs.readFileSync('vercel.json'));
  assert.ok(config.functions['api/share-image.js'].includeFiles.includes('assets/shop/supplier-details/**'));
  for(const id of ['motion9-258','funomad-indie5']){
   const p=catalog.products.find(p=>p.id===id);assert.ok(p);
   const handler=createImageHandler({productFor:()=>p,fetchImpl:async()=>{throw Error('Local source must not fetch network')}}),res=response();
   await handler({url:'/share-image.jpg?kind=product&id='+id,method:'GET'},res);
   assert.equal(res.code,200);assert.equal(res.headers['X-Nadaun-Share-Image'],'product');
   const info=await sharp(res.body).metadata();assert.equal(info.width,1200);assert.equal(info.height,630);
  }
 });
