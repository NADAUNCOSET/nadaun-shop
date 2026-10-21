const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {DatabaseSync}=require('node:sqlite');
const {calculate,validate}=require('../../assets/shop/gift-pricing.js');
const {giftRequest,quoteGift}=require('../../server/commerce/gift-orders.cjs');
const {giftAdminService}=require('../../server/commerce/gift-admin.cjs');
const {endpoint}=require('../../server/commerce/http.cjs');
const {sessions}=require('../../server/commerce/security.cjs');
const key='ab'.repeat(32),clock=()=>Date.parse('2026-10-22T01:00:00Z');
const pricing={revision:'1'.repeat(16),minimum_quantity:100,vat_basis_points:1000,observed_at:'2026-09-08T01:00:00Z',options:[{id:'2'.repeat(16),label:'기본',tiers:[{minimum_quantity:100,unit_price_ex_vat:4891},{minimum_quantity:200,unit_price_ex_vat:4820}]},{id:'3'.repeat(16),label:'인쇄 (+270원)',tiers:[{minimum_quantity:100,unit_price_ex_vat:5160},{minimum_quantity:200,unit_price_ex_vat:5090}]}]};
const product={id:'2614627',name:'테스트 상품',category_ids:['1'],image:'/test.png',pricing,pricing_available:true};
test('quantity boundaries, full option prices and subtotal VAT rounding match source formula',()=>{
 assert.equal(calculate(pricing,99,pricing.options[0].id).status,'below_minimum');
 for(const [qty,unit] of [[100,4891],[150,4891],[199,4891],[200,4820],[201,4820]]){
  const p=calculate(pricing,qty,pricing.options[0].id);assert.equal(p.unit_price_ex_vat,unit);assert.equal(p.total_including_vat,Math.round(unit*qty*1.1));
 }
 assert.equal(calculate(pricing,150,pricing.options[1].id).unit_price_ex_vat,5160);
 assert.equal(calculate(pricing,101,pricing.options[0].id).total_including_vat,543390);
 for(const q of [0,1.5,'100',100001])assert.throws(()=>calculate(pricing,q,pricing.options[0].id));
 assert.throws(()=>calculate(pricing,100,'fake'));
 assert.throws(()=>validate({...pricing,vat_basis_points:0}));
 const bad=structuredClone(pricing);bad.options[0].tiers.reverse();assert.throws(()=>validate(bad));
});
test('server captures its own immutable estimate and rejects stale revisions and invented options',()=>{
 const input={product_id:product.id,quantity:101,option_id:pricing.options[0].id,pricing_revision:pricing.revision,estimate:{total_including_vat:1},unit_price:1};
 const r=giftRequest(()=>product,input,clock);assert.equal(r.gift.estimate.total_including_vat,543390);assert.equal(r.lines[0].unit_price,null);assert.equal(r.lines[0].option,'기본');
 for(const mutation of [{pricing_revision:'0'.repeat(16)},{pricing_revision:undefined},{option_id:'fake'}])assert.throws(()=>giftRequest(()=>product,{...input,...mutation},clock));
 const quoted=quoteGift(r.lines,{gift_conditions_confirmed:true,gift_prices:[{id:r.lines[0].id,option:'기본',unit_price:4891,price_basis:'ex_vat'}],gift_shipping:4400});
 assert.equal(quoted.subtotal,543390);assert.equal(quoted.total,547790);assert.equal(quoted.lines[0].line_total,543390);
 assert.equal(r.gift.estimate.total_including_vat,543390);
 assert.throws(()=>quoteGift(r.lines,{gift_conditions_confirmed:true,gift_prices:[{id:r.lines[0].id,option:'기본',unit_price:4891,price_basis:'bad'}],gift_shipping:0}));
});
function fixture(){
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync('server/commerce/schema.sql','utf8'));
 const db={query:async(statement,params=[])=>sql.prepare(statement).all(...params)};
 const service=giftAdminService({db,catalog:()=>({meta:{product_count:1},categories:[],products:[product]}),product:id=>id===product.id?product:null,dataKey:key,clock});
 const input={version:0,supplier:{company:'검증 공급업체',phone:'02-000-0000',email:'fixture@example.com'},terms:{printing:'100개 1000원',external_display:'unknown'},evidence:{kind:'owner_export',reference:'fixture.csv',observed_at:'2026-10-21T01:00:00Z'}};
 return {sql,db,service,input};
}
test('supplier records are encrypted, exact-SKU linked, versioned and never inferred from maker labels',async()=>{
 const f=fixture();assert.equal((await f.service.get(product.id)).supplier_record,null);
 let r=await f.service.save(product.id,f.input,'verified-admin');assert.equal(r.supplier_record.version,1);assert.equal(r.supplier_record.supplier.phone,f.input.supplier.phone);
 const raw=f.sql.prepare('SELECT * FROM shop_gift_suppliers').get();assert(!JSON.stringify(raw).includes('fixture@example.com'));assert(!JSON.stringify(raw).includes('verified-admin'));
 await assert.rejects(f.service.save(product.id,f.input,'other'),{status:409});
 await f.service.save(product.id,{...f.input,version:1,supplier:{company:'검증 변경업체'}},'verified-admin');assert.equal(f.sql.prepare('SELECT COUNT(*) n FROM shop_gift_suppliers').get().n,2);
 assert.equal((await f.service.list({status:'supplier'})).total,1);assert.equal((await f.service.list({status:'missing_supplier'})).total,0);
 await assert.rejects(f.service.get('missing'),{status:400});
 await assert.rejects(f.service.save('999',f.input,'a'),{status:404});
 await assert.rejects(f.service.save(product.id,{...f.input,version:2,evidence:{...f.input.evidence,observed_at:'2099-01-01T00:00:00Z'}},'a'),{status:400});
 await assert.rejects(f.service.save(product.id,{...f.input,version:2,evidence:{...f.input.evidence,observed_at:'2026-09-01T00:00:00Z'}},'a'),{status:409});
 assert.equal((await f.service.get(product.id)).supplier_record.version,2);
});
test('supplier endpoints require admin session and same-site write origin; actor input is ignored',async()=>{
 const f=fixture(),handler=endpoint({service:{},repo:{limit:async()=>{}},giftAdmin:f.service,sessionKey:key,password:'unused',enabled:false,clock});
 const admin='__Host-nadaun-admin='+sessions(key,clock).issue('operator','admin',3600);
 async function call(action,method='GET',body,headers={}){const res={setHeader(){},status(n){this.code=n;return this;},json(v){this.body=v;return this;}};await handler({url:'/api/orders?action='+action,method,body,headers},res);return res;}
 assert.equal((await call('admin-gift-products')).code,401);
 assert.equal((await call('admin-gift-products','GET',undefined,{cookie:admin})).code,200);
 assert.equal((await call('admin-gift-supplier-save','POST',{...f.input,product_id:product.id},{cookie:admin,origin:'https://evil.invalid'})).code,403);
 const r=await call('admin-gift-supplier-save','POST',{...f.input,product_id:product.id,actor:'forged'},{cookie:admin,origin:'https://order.nadaun.co'});assert.equal(r.code,200);
});
