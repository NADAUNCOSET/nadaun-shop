const test=require('node:test');const assert=require('node:assert/strict');
const {render,createHandler}=require('../../server/promotions.cjs');
const campaign={id:'event',title:'기간 행사',terms:'마일리지 즉시 할인 아님',start_at:'2026-10-12T00:00:00+09:00',end_at:'2026-11-16T00:00:00+09:00'};
const product={id:'p',kind:'purchase',name:'카메라',image:'/camera.jpg',price:10000,sale_price:8000,offers:[{source:'digitalcp'}],promotions:[campaign]};
test('SSR expires at the exact KST boundary and keeps the verified supplier selling amount',()=>{
 const catalog={products:[product]};const start=Date.parse(campaign.start_at),end=Date.parse(campaign.end_at);
 assert.match(render(catalog,start),/10,000원/);assert.match(render(catalog,end-1),/기간 행사/);
 assert.doesNotMatch(render(catalog,start-1),/item.html/);assert.doesNotMatch(render(catalog,end),/item.html/);
 assert.match(render(catalog,start),/마일리지 즉시 할인 아님/);
});
test('HTML route evaluates the current period without shared caching and handles HEAD',()=>{
 let now=Date.parse(campaign.start_at);const handler=createHandler({catalog:{products:[product]},template:'<main id="main">old</main>',clock:()=>now});
 function response(){return {headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.code=n;return this;},end(b){this.body=b;return this;}};}
 let r=response();handler({method:'GET'},r);assert.equal(r.code,200);assert.equal(r.headers['Cache-Control'],'no-store');assert.match(r.body,/카메라/);
 now=Date.parse(campaign.end_at);r=response();handler({method:'GET'},r);assert.doesNotMatch(r.body,/카메라/);
 r=response();handler({method:'HEAD'},r);assert.equal(r.body,'');
 r=response();handler({method:'POST'},r);assert.equal(r.code,405);
});
test('an active variant remains visible when its family representative is outside the campaign',()=>{
 const catalog={products:[{...product,promotions:[]},{...product,id:'variant',listing_id:'p'}]};
 assert.match(render(catalog,Date.parse(campaign.start_at)),/id=variant/);
 assert.doesNotMatch(render(catalog,Date.parse(campaign.start_at)),/id=p"/);
});
