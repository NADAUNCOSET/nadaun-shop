const {test}=require('node:test');
const assert=require('node:assert/strict');
const {render,createHandler}=require('../../server/catalog-pages.cjs');
const brands=[{id:'sample',name:'샘플',purchase_count:2,rental_count:1}];
const categories=[{id:'type-a',name:'A 마운트',scope:'product',parent_id:null},{id:'type-b',name:'B 마운트',scope:'product',parent_id:null},{id:'rent:camera',name:'카메라',scope:'rental-product',parent_id:null}];
const product=(id,kind,type,extra={})=>({id,name:id,kind,type_ids:[type],brand_id:'sample',category_ids:[],offers:[],price:42000,status:'available',image:'/sample.jpg',discovery:{search_terms:[]},...extra});
const catalog={brands,categories,products:[product('lens-a','purchase','type-a',{listing_id:'lens-a'}),product('lens-b','purchase','type-b',{listing_id:'lens-a'}),product('camera-rent','rental','rent:camera',{rental:{price:42000,period:'1일'}})]};
test('request selects rental before any JavaScript runs',async()=>{
 const x=await render(catalog,new URLSearchParams('kind=rental'));
 assert.equal(x.status,200);assert.deepEqual(x.rows.map(p=>p.id),['camera-rent']);
 assert.match(x.body,/카메라/);assert.match(x.canonical,/kind=rental$/);
 assert.ok(!x.body.includes('lens-a'));assert.ok(!x.noindex);
});
test('mount-specific family variant is present in initial HTML',async()=>{
 const x=await render(catalog,new URLSearchParams('type=type-b'),'sample','/brands/sample.html');
 assert.deepEqual(x.rows.map(p=>p.id),['lens-b']);assert.match(x.body,/id=lens-b/);
 assert.equal(x.canonical,'https://shop.nadaun.co/brands/sample.html?type=type-b');
});
test('camera compatibility uses the browser selection and a unique canonical',async()=>{
 const data={...catalog,camera_models:[{id:'sample-camera',name:'샘플 카메라'}],products:catalog.products.map(p=>({...p,compatible_camera_model_ids:p.id==='lens-b'?['sample-camera']:[]}))};
 const x=await render(data,new URLSearchParams('camera=sample-camera'));
 assert.deepEqual(x.rows.map(p=>p.id),['lens-b']);assert.match(x.heading||x.body,/샘플 카메라용/);
 assert.equal(x.canonical,'https://shop.nadaun.co/catalog.html?camera=sample-camera');
 assert.equal((await render(data,new URLSearchParams('camera=missing'))).status,404);
});
test('invalid routes return 404; free text and sorting do not create indexable search pages',async()=>{
 for(const params of ['page=999','page=-1','type=missing','kind=invalid','kind=rental&type=type-a'])assert.equal((await render(catalog,new URLSearchParams(params))).status,404);
 assert.equal((await render(catalog,new URLSearchParams(),'missing')).status,404);
 assert.equal((await render(catalog,new URLSearchParams('q=lens'))).noindex,true);
 assert.equal((await render(catalog,new URLSearchParams('sort=low'))).noindex,true);
});
test('rewritten request preserves brand metadata and HEAD semantics',async()=>{
 const handler=createHandler({catalog,template:'<html><head><title>old</title><meta name="robots" content="index,follow,max-image-preview:large"><link rel="canonical" href="old"></head><body data-brand=""><main id="main"></main></body></html>'});
 const response=()=>({headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.code=n;return this;},end(body){this.body=body;return this;}});
 let r=response();await handler({method:'GET',url:'/api/search?view=catalog&brand=sample&type=type-b'},r);
 assert.equal(r.code,200);assert.match(r.body,/data-brand="sample"/);assert.match(r.body,/brands\/sample.html\?type=type-b/);assert.match(r.body,/id=lens-b/);
 r=response();await handler({method:'HEAD',url:'/catalog.html?kind=rental'},r);assert.equal(r.code,200);assert.equal(r.body,'');
});
