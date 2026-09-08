const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {DatabaseSync}=require('node:sqlite');
const root=path.resolve(__dirname,'../..');
const {repository,orderService}=require('../../server/commerce/orders.cjs');
const {quoteCatalog}=require('../../server/commerce/pricing.cjs');
const {protect,sessions,passwordHash,hash}=require('../../server/commerce/security.cjs');
const {endpoint}=require('../../server/commerce/http.cjs');
const {database}=require('../../server/commerce/d1.cjs');
const {toss}=require('../../server/commerce/toss.cjs');
const secret='ab'.repeat(32),owner=hash('customer-one'),other=hash('customer-two');
const customer={name:'테스트 고객',phone:'010-0000-0000',postcode:'01234',address:'테스트시 테스트로 123',address_detail:'테스트동',consent:true};
const item={id:'p1',option:'블랙',quantity:2};
function fixture(){
 let now=Date.parse('2026-09-08T00:00:00Z');const clock=()=>now;
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync(path.join(root,'server/commerce/schema.sql'),'utf8'));
 const db={async batch(statements){sql.exec('BEGIN');try{const result=statements.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return result;}catch(error){sql.exec('ROLLBACK');throw error;}},async query(statement,params=[]){return (await this.batch([{sql:statement,params}]))[0];}};
 const catalog={meta:{synced_at:new Date(now).toISOString(),revision:'fixture'},redirects:{old:'p1'},products:[
  {id:'p1',kind:'purchase',name:'카메라',status:'inquiry',price:10000,sale_price:9000,offers:[{source:'smartstore'}],shipping_class:'standard',image:'/camera.jpg'},
  {id:'p2',kind:'purchase',name:'중량 스탠드',status:'inquiry',price:20000,sale_price:10000,offers:[{source:'kpp'}],shipping_class:'heavy_stand',image:'/stand.jpg'}]};
 const details={p1:{options:[{name:'블랙',additional_price:1000}]},p2:{}};
 const repo=repository(db,clock),calls=[],remote={};
 const payment={clientKey:'test_gck_fixture',mode:'test',async confirm(input,key){calls.push({input,key});Object.assign(remote,{orderId:input.orderId,paymentKey:input.paymentKey,totalAmount:input.amount,currency:'KRW',status:'DONE'});},async get(){return {...remote};}};
 const service=orderService({repo,catalog,detail:p=>details[p.id],dataKey:secret,payment,clock});
 const create=()=>service.create(owner,'idempotency_fixture',{customer,items:[item],total:1});
 async function started(){let order=await create();order=await service.approve(order.id,{version:order.version,stock_confirmed:true});await service.start(order.id,owner,order.quote_version);return await repo.get(order.id);}
 return {sql,db,repo,catalog,details,clock,advance:ms=>now+=ms,service,payment,calls,remote,create,started};
}
test('server prices, option quantity and once-per-order shipping override client totals',()=>{
 const f=fixture();let q=quoteCatalog(f.catalog,p=>f.details[p.id],[item],f.clock);assert.equal(q.total,24500);
 q=quoteCatalog(f.catalog,p=>f.details[p.id],[item,{id:'p2',option:'',quantity:3}],f.clock);assert.equal(q.shipping,7000);assert.equal(q.total,87000);
});
test('reject stale snapshots, sold-out/rental products, changed options and canonical duplicates',()=>{
 for(const mutate of [f=>f.advance(49*3600*1000),f=>f.catalog.products[0].status='soldout',f=>f.catalog.products[0].kind='rental',f=>f.details.p1.options_require_confirmation=true,f=>f.details.p1.options[0].name='화이트']){
  const f=fixture();mutate(f);assert.throws(()=>quoteCatalog(f.catalog,p=>f.details[p.id],[item],f.clock));
 }
 const f=fixture();assert.throws(()=>quoteCatalog(f.catalog,p=>f.details[p.id],[item,{...item,id:'old'}],f.clock));
 assert.throws(()=>quoteCatalog(f.catalog,p=>f.details[p.id],[{...item,quantity:1.5}],f.clock));
});
test('retry creates one encrypted order and one event; changed payload conflicts',async()=>{
 const f=fixture(),a=await f.create(),b=await f.create();assert.equal(a.id,b.id);assert.equal((await f.repo.events(a.id)).length,1);assert.equal(f.sql.prepare('SELECT COUNT(*) AS n FROM shop_orders').get().n,1);
 const raw=await f.repo.get(a.id);assert.ok(!raw.customer_cipher.includes(customer.name));assert.equal(protect(secret).decrypt(raw.customer_cipher).phone,customer.phone);assert.ok(!('customer' in a));
 await assert.rejects(f.service.create(owner,'idempotency_fixture',{customer,items:[{...item,quantity:3}]}),{status:409});
 await assert.rejects(f.service.get(a.id,other),{status:404});assert.deepEqual(await f.service.list(other),[]);
});
test('database batch rolls back order changes when audit write fails',async()=>{
 const f=fixture(),a=await f.create(),raw=await f.repo.get(a.id);f.sql.exec('DROP TABLE shop_order_events');
 await assert.rejects(f.repo.patch(raw,{state:'APPROVED'},'owner','quote_approved'));assert.equal((await f.repo.get(a.id)).state,'REQUESTED');
});
test('approval requires explicit stock confirmation and current version; conflicting writes do not duplicate events',async()=>{
 const f=fixture(),a=await f.create();await assert.rejects(f.service.approve(a.id,{version:0}),{status:409});
 const results=await Promise.allSettled([1,2].map(()=>f.service.approve(a.id,{version:0,stock_confirmed:true})));
 assert.equal(results.filter(x=>x.status==='fulfilled').length,1);assert.equal((await f.repo.events(a.id)).length,2);
 await assert.rejects(f.service.ship(a.id,{version:1,carrier:'택배사',tracking:'123456789'}),{status:409});
});
test('payment start rejects unapproved, stale quote version and expired quotes',async()=>{
 const f=fixture(),a=await f.create();await assert.rejects(f.service.start(a.id,owner,0),{status:409});const b=await f.service.approve(a.id,{version:0,stock_confirmed:true});
 await assert.rejects(f.service.start(a.id,owner,0),{status:409});f.advance(31*60*1000);await assert.rejects(f.service.start(a.id,owner,b.quote_version),{status:409});assert.equal(f.calls.length,0);
});
test('verified payment marks paid once and only paid orders can receive shipment',async()=>{
 const f=fixture();f.payment.mode='live';const a=await f.started(),input={paymentKey:'payment_fixture_123',amount:a.total};
 const result=await f.service.confirm(a.id,owner,input);assert.equal(result.state,'PAID');assert.equal(f.calls.length,1);assert.equal(f.calls[0].key,a.confirm_key);
 assert.equal((await f.service.confirm(a.id,owner,input)).state,'PAID');assert.equal(f.calls.length,1);
 const shipped=await f.service.ship(a.id,{version:result.version,carrier:'CJ대한통운',tracking:'123456789012'});assert.equal(shipped.fulfillment,'shipped');
 assert.equal((await f.repo.events(a.id)).filter(x=>x.action==='payment_done').length,1);
});
test('test payments cannot ship and live keys cannot confirm a test-mode order',async()=>{
 const f=fixture(),a=await f.started(),input={paymentKey:'payment_fixture_123',amount:a.total};
 const paid=await f.service.confirm(a.id,owner,input);assert.equal(paid.payment_mode,'test');
 await assert.rejects(f.service.ship(a.id,{version:paid.version,carrier:'택배사',tracking:'123456789'}),{status:409});
 f.payment.mode='live';await assert.rejects(f.service.confirm(a.id,owner,input),{status:409});await assert.rejects(f.service.reconcile(a.id),{status:409});
});
test('forged amount, foreign payment and inconsistent provider response never become paid',async()=>{
 const f=fixture(),a=await f.started();await assert.rejects(f.service.confirm(a.id,owner,{paymentKey:'payment_fixture_123',amount:1}),{status:409});assert.equal(f.calls.length,0);
 f.payment.confirm=async()=>{};Object.assign(f.remote,{orderId:'different-order',paymentKey:'payment_fixture_123',totalAmount:a.total,currency:'KRW',status:'DONE'});
 await assert.rejects(f.service.confirm(a.id,owner,{paymentKey:'payment_fixture_123',amount:a.total}),{status:502});assert.equal((await f.repo.get(a.id)).state,'CONFIRMING');
 await assert.rejects(f.service.confirm(a.id,owner,{paymentKey:'different_key_123',amount:a.total}),{status:409});
});
test('lost POST response recovers by authoritative GET without creating a new payment',async()=>{
 const f=fixture(),a=await f.started(),original=f.payment.confirm;
 f.payment.confirm=async(...args)=>{await original(...args);throw Error('response lost');};
 assert.equal((await f.service.confirm(a.id,owner,{paymentKey:'payment_fixture_123',amount:a.total})).state,'PAID');assert.equal(f.calls.length,1);
});
test('POST that never arrived retries with the persisted idempotency key',async()=>{
 const f=fixture(),a=await f.started(),original=f.payment.confirm;let count=0;const keys=[];
 Object.assign(f.remote,{orderId:a.id,paymentKey:'payment_fixture_123',totalAmount:a.total,currency:'KRW',status:'READY'});
 f.payment.confirm=async(...args)=>{keys.push(args[1]);if(!count++)throw Error('network unavailable');return original(...args);};
 assert.equal((await f.service.confirm(a.id,owner,{paymentKey:'payment_fixture_123',amount:a.total})).state,'PAID');assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);
});
test('unknown payment stays unfulfilled; cancellation cannot regress to paid',async()=>{
 const f=fixture(),a=await f.started();f.payment.confirm=async()=>{};Object.assign(f.remote,{orderId:a.id,paymentKey:'payment_fixture_123',totalAmount:a.total,currency:'KRW',status:'IN_PROGRESS'});
 await assert.rejects(f.service.confirm(a.id,owner,{paymentKey:'payment_fixture_123',amount:a.total}),{status:503});assert.equal((await f.repo.get(a.id)).fulfillment,'unfulfilled');
 f.remote.status='CANCELED';assert.equal((await f.service.reconcile(a.id)).state,'CANCELED');f.remote.status='DONE';await assert.rejects(f.service.reconcile(a.id),{status:409});
});
test('signed sessions expire, cannot swap roles and detect tampering; ciphertext authenticates',()=>{
 let time=100;const s=sessions(secret,()=>time),token=s.issue('owner','admin',1);assert.equal(s.read(token,'admin'),'owner');assert.equal(s.read(token,'customer'),null);assert.equal(s.read(token+'x','admin'),null);time=1101;assert.equal(s.read(token,'admin'),null);
 const cipher=protect(secret),value=cipher.encrypt(customer);assert.throws(()=>protect('cd'.repeat(32)).decrypt(value));
});
test('persistent rate limits survive requests, reset by window and expire old buckets',async()=>{
 const f=fixture();await f.repo.limit('fixture',1,60);await assert.rejects(f.repo.limit('fixture',1,60),{status:429});f.advance(121000);await f.repo.limit('fixture',1,60);assert.equal(f.sql.prepare('SELECT COUNT(*) AS n FROM shop_rate_limits').get().n,1);
});
test('HTTP authorizes admin and customer separately, enforces origin, uses private cookies',async()=>{
 const f=fixture(),password=await passwordHash('fixture password only 123!');const handler=endpoint({service:f.service,repo:f.repo,sessionKey:secret,password,clock:f.clock});
 async function call(action,method='GET',body,headers={}){const res={headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.code=n;return this;},json(v){this.body=v;return this;}};await handler({url:'/api/orders?action='+action,method,body,headers:{origin:'https://shop.nadaun.co',...headers}},res);return res;}
 assert.equal((await call('admin-orders')).code,401);assert.equal((await call('login','POST',{password:'fixture password only 123!'},{origin:'https://evil.invalid'})).code,403);
 const logged=await call('login','POST',{password:'fixture password only 123!'});assert.equal(logged.code,200);const admin=logged.headers['Set-Cookie'];assert.match(admin,/Secure; HttpOnly; SameSite=Lax/);
 assert.equal((await call('admin-orders','GET',null,{cookie:admin.split(';')[0]})).code,200);
 const session=await call('session','POST',{}),cookie=session.headers['Set-Cookie'].split(';')[0];assert.equal((await call('admin-orders','GET',null,{cookie})).code,401);
 const a=await call('create','POST',{customer,items:[item]},{cookie,'idempotency-key':'http_idempotency_123'});assert.equal(a.code,201);assert.equal((await call('orders','GET',null,{cookie})).body.orders.length,1);
 assert.equal((await call('orders')).code,401);assert.equal(a.headers['Cache-Control'],'no-store');assert.equal((await call('session','POST','not json')).code,400);
});
test('D1 uses bounded parameterized batches and hides provider errors',async()=>{
 const env={SHOP_CF_ACCOUNT_ID:'a'.repeat(32),SHOP_D1_DATABASE_ID:'b'.repeat(36),SHOP_D1_API_TOKEN:'private_fixture'};let request;
 const db=database(env,async(url,options)=>{request={url,options};return{ok:true,json:async()=>({success:true,result:[{success:true,results:[{id:'ok'}]}]})};});
 assert.deepEqual(await db.query('SELECT ? AS id',['ok']),[{id:'ok'}]);assert.deepEqual(JSON.parse(request.options.body).batch[0].params,['ok']);assert.match(request.url,/api.cloudflare.com/);
 await assert.rejects(database(env,async()=>({ok:false,json:async()=>({success:false,errors:['private_fixture']})})).query('SELECT ?',['sensitive']),error=>error.status===503&&!error.message.includes('private_fixture'));
});
test('Toss uses the configured mode, Basic credentials and an idempotent confirmation',async()=>{
 const env={SHOP_PAYMENT_MODE:'test',SHOP_TOSS_CLIENT_KEY:'test_gck_fixture',SHOP_TOSS_SECRET_KEY:'test_gsk_fixture'};const calls=[];
 const payment=toss(env,async(url,options)=>{calls.push({url,options});return{ok:true,json:async()=>({status:'DONE'})};});
 await payment.confirm({paymentKey:'p',orderId:'o',amount:100},'stable-key');await payment.get('p');assert.equal(calls[0].options.headers['Idempotency-Key'],'stable-key');assert.equal(calls[0].options.headers.Authorization,'Basic '+Buffer.from('test_gsk_fixture:').toString('base64'));assert.equal(calls[1].options.method,'GET');
 assert.throws(()=>toss({...env,SHOP_PAYMENT_MODE:'live'}));
 assert.throws(()=>toss({...env,SHOP_TOSS_SECRET_KEY:'test_sk_fixture'}));
 assert.throws(()=>toss({...env,SHOP_TOSS_CLIENT_KEY:'test_ck_fixture'}));
 assert.throws(()=>toss({...env,SHOP_TOSS_SECRET_KEY:'live_gsk_fixture'}));
});
