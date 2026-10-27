const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {createRequire}=require('node:module');
const {pathToFileURL}=require('node:url');
const root=process.cwd();
const product={id:'saeki-coming',name:'TEST 출시전 카메라',brand_id:'test',kind:'purchase',release_status:'coming_soon',
 price:0,sale_price:0,status:'soldout',supplier_status:'soldout',image:'/assets/shop/nadaun-logo.png',detail_bucket:'00',
 category_ids:[],type_ids:[],promotion_ids:['source:promotion'],offers:[{source:'saeki'}],
 discovery:{description:'TEST 구매 안내. 출시 예정 · 가격 미공개. 출시 일정 상담.',tags:['TEST','제품 구매'],categories:[]}};
const catalog={products:[product],brands:[{id:'test',name:'TEST',aliases:[]}],categories:[],redirects:{},meta:{revision:'fixture'}};
function load(file){
 const filename=path.join(root,file),realRequire=createRequire(filename),module={exports:{}};
 const readFileSync=(filename,...rest)=>String(filename)===path.join(root,'data/catalog/catalog.json')?JSON.stringify(catalog):fs.readFileSync(filename,...rest);
 vm.runInNewContext(fs.readFileSync(filename,'utf8'),{module,exports:module.exports,
  require:name=>name==='node:fs'?{...fs,readFileSync}:realRequire(name),process,URL,URLSearchParams,console}, {filename});
 return module.exports;
}
function clearRelease(html){
 assert.match(html,/출시 예정 · 가격 미공개/);assert.match(html,/출시 일정 상담/);
 assert.doesNotMatch(html,/0원|품절|재입고 문의|SALE|PROMOTION/);
}
test('SSR product retains sharing metadata and never emits a purchasable Offer for a release preview',()=>{
 const handler=load('api/product.js');let body='';
 handler({url:'/item.html?id='+product.id,method:'GET'}, {setHeader(){},status(){return this},end(v){body=v}});
 const main=body.match(/<main[^>]*>([\s\S]*?)<\/main>/)[1];clearRelease(main);
 assert.match(body,/\/share-image\.jpg\?kind=product&amp;id=saeki-coming/);
 const schemas=[...body.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map(m=>JSON.parse(m[1]));
 const schema=schemas.find(p=>p['@type']==='Product');assert.equal(schema.name,product.name);assert.equal(schema.offers,undefined);
});
test('unified search finds explicit release intent and shows it separately from sold-out stock',()=>{
 const search=load('server/shop-search.cjs');
 assert.ok(search.results('출시 예정').some(p=>p.id===product.id));
 clearRelease(search.render(new URLSearchParams({q:product.id,scope:'purchase'})).body);
});
test('release products are not discount or promotion products, even with stale monetary fields',async()=>{
 const tools=await import(pathToFileURL(path.join(root,'assets/shop/catalog-tools.js')));
 const p={...product,price:10000,sale_price:0,offers:[{source:'smartstore'}]};
 assert.equal(tools.isDiscounted(p),false);assert.equal(tools.isPromotion(p),false);assert.equal(tools.matchesBenefit(p),false);
 assert.equal(tools.isDiscounted({...p,release_status:undefined}),true);
});
test('browser card and hydrated detail show release messaging without mounting purchase inputs',async()=>{
 const {compatibilitySection}=await import(pathToFileURL(path.join(root,'assets/shop/compatibility.js')));
 const source=fs.readFileSync(path.join(root,'assets/shop/shop.js'),'utf8');
 const card=source.match(/^function productCard\(p\).*$/m)[0];
 const detail=source.slice(source.indexOf('async function renderItem()'),source.indexOf('\nfunction renderCategories()'));
 const helpers=source.split('\n').filter(line=>/^(const (esc|safe|won|money|brandHref)=|function discoveryLinks\()/.test(line)).join('\n');
 const tags=new Map(),main={innerHTML:''};let mounts=0;
 const context={URL,URLSearchParams,console,main,location:{origin:'https://shop.nadaun.co'},
  brandMap:new Map([['test',{name:'TEST'}]]),params:new URLSearchParams({id:product.id}),data:catalog,
  isDiscounted:()=>true,isPromotion:()=>true,compatibilitySection,
  document:{querySelector:selector=>{if(!tags.has(selector))tags.set(selector,{});return tags.get(selector)},querySelectorAll:()=>[]},
  fetch:async()=>({ok:true,json:async()=>({[product.id]:{options:[{name:'옵션',additional_price:10000}],images:{main:[product.image]}}})}),
  mountPurchase:()=>{mounts++}};
 vm.createContext(context);vm.runInContext(helpers+'\n'+card+'\n'+detail,context);
 clearRelease(vm.runInContext('productCard(data.products[0])',context));
 await vm.runInContext('renderItem()',context);clearRelease(main.innerHTML);assert.equal(mounts,0);
 assert.doesNotMatch(main.innerHTML,/10,000원/);
});
