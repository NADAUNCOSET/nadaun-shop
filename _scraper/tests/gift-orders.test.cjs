const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {DatabaseSync}=require('node:sqlite');
const {repository,orderService}=require('../../server/commerce/orders.cjs');
const {giftRequest,quoteGift}=require('../../server/commerce/gift-orders.cjs');
const {endpoint}=require('../../server/commerce/http.cjs');
const {hash,protect,sessions}=require('../../server/commerce/security.cjs');
const secret='ef'.repeat(32),clock=()=>Date.parse('2026-10-21T09:00:00Z'),owner=hash('gift-fixture');
const product={id:'2611146',name:'테스트 기프트',image:'/test.png',soldout:false};
const customer={name:'테스트 고객',phone:'010-0000-0000',postcode:'01234',address:'테스트시 테스트로 123',address_detail:'테스트동',consent:true};
const gift={product_id:product.id,quantity:5000,variant:'흰색',printing:'로고 1도',packaging:'개별 포장',requested_date:'2026-10-30',notes:'인쇄 시안 확인 후 제작'};
function fixture(){
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync(new URL('../../server/commerce/schema.sql',`file://${__filename}`),'utf8'));
 const db={async batch(statements){sql.exec('BEGIN');try{const result=statements.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return result;}catch(error){sql.exec('ROLLBACK');throw error;}},async query(statement,params=[]){return (await this.batch([{sql:statement,params}]))[0];}};
 const repo=repository(db,clock),payment={mode:'test',prepare(row){return {amount:row.total,orderId:row.id};}};
 const service=orderService({repo,catalog:{meta:{synced_at:'2000-01-01'},products:[]},detail:()=>null,giftProduct:id=>id===product.id?product:null,dataKey:secret,sessionKey:secret,payment,clock});
 const create=(changes={},key='gift_fixture_request_01')=>service.createGift(owner,key,{customer,gift,...changes});
 const approval=o=>({version:o.version,stock_confirmed:true,gift_conditions_confirmed:true,gift_prices:o.lines.map(p=>({id:p.id,option:p.option,unit_price:2100})),gift_shipping:6000});
 return {sql,db,repo,service,create,approval};
}
test('gift request accepts bulk quantity, ignores client price, encrypts customer and is idempotent',async()=>{
 const f=fixture(),a=await f.create({total:1,gift:{...gift,unit_price:1}}),b=await f.create();
 assert.equal(a.id,b.id);assert.equal(a.total,null);assert.equal(a.lines[0].quantity,5000);assert.equal(a.lines[0].unit_price,null);assert.equal(a.gift.printing,gift.printing);
 assert.equal(a.customer,undefined);assert.equal((await f.repo.events(a.id)).length,1);
 const row=await f.repo.get(a.id);assert.ok(!row.customer_cipher.includes(customer.phone));assert.equal(protect(secret).decrypt(row.customer_cipher).gift.packaging,gift.packaging);
 await assert.rejects(f.create({gift:{...gift,printing:'다른 인쇄'}}),{status:409});
 await assert.rejects(f.service.get(a.id,hash('other')),{status:404});
});
test('gift rejects unknown product, soldout, invalid quantities, past/impossible dates and oversized notes',()=>{
 for(const mutation of [{product_id:'404'},{product_id:2611146},{quantity:0},{quantity:1.5},{quantity:100001},{quantity:'100'},{requested_date:'2026-10-20'},{requested_date:'2026-02-30'},{notes:'x'.repeat(1001)}])assert.throws(()=>giftRequest(id=>id===product.id?product:null,{...gift,...mutation},clock));
 assert.throws(()=>giftRequest(()=>({...product,soldout:true}),gift,clock),{status:409});
 for(const quantity of [1,100000])assert.equal(giftRequest(()=>product,{...gift,quantity,requested_date:'2026-10-21'},clock).lines[0].quantity,quantity);
});
test('gift quote requires fresh supplier conditions and rejects spoofed lines, missing shipping and excessive total',async()=>{
 const f=fixture(),a=await f.create(),base=f.approval(a);
 for(const mutation of [{stock_confirmed:false},{gift_conditions_confirmed:false},{gift_prices:[]},{gift_prices:[{...base.gift_prices[0],id:'fake'}]},{gift_prices:[{...base.gift_prices[0],unit_price:1.5}]},{gift_prices:[{...base.gift_prices[0],unit_price:100000000}]},{gift_shipping:undefined},{gift_shipping:-1}])await assert.rejects(f.service.approve(a.id,{...base,...mutation}));
 assert.equal((await f.service.get(a.id,owner)).state,'REQUESTED');
});
test('gift request -> admin quote -> customer payment uses only confirmed VAT-inclusive amount',async()=>{
 const f=fixture(),a=await f.create();await assert.rejects(f.service.start(a.id,owner,0),{status:409});
 const b=await f.service.approve(a.id,f.approval(a),'operator');assert.equal(b.total,10506000);assert.equal(b.subtotal,10500000);assert.equal(b.gift.requested_date,gift.requested_date);
 assert.deepEqual(await f.service.start(b.id,owner,b.quote_version),{amount:10506000,orderId:b.id});
 await assert.rejects(f.service.approve(b.id,f.approval(b)),{status:409});
});
test('gift-only HTTP feature gate permits requests while purchases and payments remain disabled',async()=>{
 const f=fixture(),handler=endpoint({service:f.service,repo:f.repo,sessionKey:secret,password:'unused',enabled:false,rentalEnabled:false,giftEnabled:true,clock});
 async function call(action,method='GET',body,headers={}){const res={headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.code=n;return this;},json(v){this.body=v;return this;}};await handler({url:'/api/orders?action='+action,method,body,headers:{origin:'https://shop.nadaun.co',...headers}},res);return res;}
 const config=(await call('config')).body;assert.equal(config.giftRequestsEnabled,true);assert.equal(config.ordersEnabled,false);
 const start=await call('session','POST',{}),cookie=start.headers['Set-Cookie'].split(';')[0],headers={cookie,'idempotency-key':'gift_http_fixture_01'};
 assert.equal((await call('gift-create','POST',{customer,gift},{...headers,origin:'https://evil.invalid'})).code,403);
 const created=await call('gift-create','POST',{customer,gift},headers);assert.equal(created.code,201);assert.equal((await call('orders','GET',undefined,{cookie})).body.orders.length,1);
 assert.equal((await call('gift-create','POST',{customer,gift})).code,401);
 assert.equal((await call('admin-orders','GET',undefined,{cookie})).code,401);
 for(const action of ['create','rental-create','start'])assert.equal((await call(action,'POST',{},headers)).code,503);
 const adminCookie='__Host-nadaun-admin='+sessions(secret,clock).issue('owner','admin',3600);
 const approved=await call('admin-approve','POST',{id:created.body.order.id,...f.approval(created.body.order)},{cookie:adminCookie,origin:'https://order.nadaun.co'});assert.equal(approved.code,200);
 assert.equal((await call('admin-orders','GET',undefined,{cookie:adminCookie})).body.orders[0].gift.printing,gift.printing);
});
test('gift HTTP gate remains closed by default even when normal orders are enabled',async()=>{
 const f=fixture(),handler=endpoint({service:f.service,repo:f.repo,sessionKey:secret,password:'unused',enabled:true,clock});
 const res={setHeader(){},status(n){this.code=n;return this;},json(v){this.body=v;return this;}};
 await handler({url:'/api/orders?action=gift-create',method:'POST',headers:{origin:'https://shop.nadaun.co'},body:{customer,gift}},res);assert.equal(res.code,503);
});


test('source withdrawal after a request prevents quote/payment but preserves customer order history',async()=>{
 const f=fixture(),requested=await f.create();
 try{
  product.source_status='withdrawn';
  assert.throws(()=>giftRequest(()=>product,gift,clock),{status:409});
  await assert.rejects(f.service.approve(requested.id,f.approval(requested)),{status:409});
  assert.equal((await f.service.get(requested.id,owner)).state,'REQUESTED');
  delete product.source_status;
  const approved=await f.service.approve(requested.id,f.approval(requested));
  product.source_status='withdrawn';
  await assert.rejects(f.service.start(approved.id,owner,approved.quote_version),{status:409});
  assert.equal((await f.service.get(approved.id,owner)).state,'APPROVED');
 }finally{delete product.source_status;}
});
