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
const {documentService,managementKey}=require('../../server/commerce/documents.cjs');
const {evidenceFields}=require('../../server/commerce/evidence.cjs');
const {inicis}=require('../../server/commerce/inicis.cjs');
const secret='ab'.repeat(32),owner=hash('customer-one'),other=hash('customer-two');
const customer={name:'테스트 고객',phone:'010-0000-0000',postcode:'01234',address:'테스트시 테스트로 123',address_detail:'테스트동',consent:true};
const item={id:'p1',option:'블랙',quantity:2};
test('supplier variant availability is enforced before a server quote is created',()=>{
 for(const state of [{disabled:true},{soldout:true},{displayed:false},{supplier_status:'soldout'},{supplier_status:'unknown'}]){
  const now=Date.now(),catalog={meta:{synced_at:new Date(now).toISOString()},redirects:{},products:[{id:'p',kind:'purchase',status:'inquiry',price:1000,offers:[]}]};
  assert.throws(()=>quoteCatalog(catalog,()=>({options:[{name:'화이트',additional_price:0,...state}]}),[{id:'p',option:'화이트',quantity:1}],()=>now),{status:409});
 }
});
function fixture({invoice=null,evidence}={}){
 let now=Date.parse('2026-09-08T00:00:00Z');const clock=()=>now;
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync(path.join(root,'server/commerce/schema.sql'),'utf8'));
 const db={async batch(statements){sql.exec('BEGIN');try{const result=statements.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return result;}catch(error){sql.exec('ROLLBACK');throw error;}},async query(statement,params=[]){return (await this.batch([{sql:statement,params}]))[0];}};
 const catalog={meta:{synced_at:new Date(now).toISOString(),revision:'fixture'},redirects:{old:'p1'},products:[
  {id:'p1',kind:'purchase',name:'카메라',status:'inquiry',price:10000,sale_price:9000,offers:[{source:'smartstore'}],shipping_class:'standard',image:'/camera.jpg'},
  {id:'p2',kind:'purchase',name:'중량 스탠드',status:'inquiry',price:20000,sale_price:10000,offers:[{source:'kpp'}],shipping_class:'heavy_stand',image:'/stand.jpg'}]};
 const details={p1:{options:[{name:'블랙',additional_price:1000}]},p2:{}};
 const repo=repository(db,clock),calls=[],remote={};
 const adapter=inicis({SHOP_PAYMENT_MODE:'test',SHOP_INICIS_MID:'INIpayTest',SHOP_INICIS_HASH_KEY:'fixture-hash-key-only'},undefined,clock);
 const payment={...adapter,async approve(auth,row){calls.push({action:'approve',auth});Object.assign(remote,{provider:'inicis',orderId:row.id,paymentKey:'approval_fixture_123',totalAmount:row.total,currency:'KRW',status:'DONE',method:evidence&&evidence.kind!=='card_receipt'?'BANK':'CARD'});return {...remote};},async netCancel(){calls.push({action:'cancel'});return {canceled:true};},async get(){calls.push({action:'get'});return {...remote};}};
 const documents=documentService({db,repo,dataKey:secret,payment,invoice,clock});
 const service=orderService({repo,catalog,detail:p=>details[p.id],dataKey:secret,payment,documents,invoiceEnabled:!!invoice,clock});
 const create=()=>service.create(owner,'idempotency_fixture',{customer,items:[item],total:1,...(evidence?{evidence}:{})});
 async function started(){let order=await create();order=await service.approve(order.id,{version:order.version,stock_confirmed:true});const prepared=await service.start(order.id,owner,order.quote_version);const row=await repo.get(order.id);row.callback={P_STATUS:'00',P_MID:'INIpayTest',P_OID:row.id,P_AMT:String(row.total),P_AUTH_TID:'authentication_fixture_123',P_IDCNAME:'fc',P_NOTI:prepared.fields.P_NOTI};return row;}
 return {sql,db,repo,catalog,details,clock,advance:ms=>now+=ms,service,payment,calls,remote,create,started,documents};
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
test('authenticated provider approval is stored once; test orders cannot ship',async()=>{
 const f=fixture(),a=await f.started(),paid=await f.service.acceptReturn(a.callback);
 assert.equal(paid.state,'PAID');assert.equal(paid.payment_mode,'test');
 assert.equal((await f.service.acceptReturn(a.callback)).state,'PAID');assert.equal(f.calls.filter(x=>x.action==='approve').length,1);
 assert.equal((await f.repo.events(a.id)).filter(x=>x.action==='payment_done').length,1);
 await assert.rejects(f.service.ship(a.id,{version:paid.version,carrier:'CJ대한통운',tracking:'123456789012'}),{status:409});
 assert.ok(!(await f.repo.get(a.id)).payment_auth_cipher.includes(a.callback.P_AUTH_TID));
});
test('foreign order, amount and invalid signed callback never reach approval',async()=>{
 for(const change of [{P_OID:'foreign_order'},{P_AMT:'1'},{P_MID:'FOREIGNMID'},{P_IDCNAME:'evil.invalid'},{P_NOTI:'forged'}]){
  const f=fixture(),a=await f.started();await assert.rejects(f.service.acceptReturn({...a.callback,...change}));assert.equal(f.calls.length,0);assert.equal((await f.repo.get(a.id)).state,'PAYMENT_PENDING');
 }
});
test('expired callback and changed environment cannot approve',async()=>{
 const f=fixture(),a=await f.started();f.advance(31*60000);await assert.rejects(f.service.acceptReturn(a.callback),{status:401});assert.equal(f.calls.length,0);
 const g=fixture(),b=await g.started();g.payment.mode='live';await assert.rejects(g.service.acceptReturn(b.callback),{status:409});assert.equal(g.calls.length,0);
});
test('simultaneous callbacks cannot double approve; a different auth token is rejected',async()=>{
 const f=fixture(),a=await f.started();const results=await Promise.allSettled([f.service.acceptReturn(a.callback),f.service.acceptReturn(a.callback)]);
 assert.ok(results.some(r=>r.status==='fulfilled'));assert.equal(f.calls.filter(x=>x.action==='approve').length,1);
 await assert.rejects(f.service.acceptReturn({...a.callback,P_AUTH_TID:'different_authentication_123'}),{status:409});
});
test('approval timeout is compensated; an uncertain cancellation stays in review',async()=>{
 for(const cancelFails of [false,true]){
  const f=fixture(),a=await f.started();let count=0;f.payment.approve=async()=>{count++;throw Error('timeout');};if(cancelFails)f.payment.netCancel=async()=>{throw Error('unreachable');};
  await assert.rejects(f.service.acceptReturn(a.callback),{status:503});assert.equal((await f.repo.get(a.id)).state,cancelFails?'PAYMENT_REVIEW':'CANCELED');
  await f.service.acceptReturn(a.callback);assert.equal(count,1);assert.equal((await f.repo.get(a.id)).fulfillment,'unfulfilled');
 }
});
test('unbound approval results are not accepted and invoke compensation',async()=>{
 const f=fixture(),a=await f.started();f.payment.approve=async()=>({provider:'inicis',orderId:'foreign',paymentKey:'approval_fixture_123',totalAmount:a.total,currency:'KRW',status:'DONE'});
 await assert.rejects(f.service.acceptReturn(a.callback),{status:503});assert.equal((await f.repo.get(a.id)).state,'CANCELED');assert.equal(f.calls[0].action,'cancel');
});
test('DB failure after approval invokes net cancellation; a lost committed DB response does not',async()=>{
 for(const committed of [false,true]){
  const f=fixture(),a=await f.started(),patch=f.repo.patch;f.repo.patch=async(...args)=>{if(args[1].state==='PAID'){if(committed)await patch(...args);throw Error('DB response lost');}return patch(...args);};
  if(committed){assert.equal((await f.service.acceptReturn(a.callback)).state,'PAID');assert.equal(f.calls.filter(x=>x.action==='cancel').length,0);}
  else{await assert.rejects(f.service.acceptReturn(a.callback));assert.equal((await f.repo.get(a.id)).state,'CANCELED');assert.equal(f.calls.filter(x=>x.action==='cancel').length,1);}
 }
});
test('live shipment queries current provider status and refuses a refunded order',async()=>{
 const f=fixture();f.payment.mode='live';const a=await f.started(),paid=await f.service.acceptReturn(a.callback);
 const shipped=await f.service.ship(a.id,{version:paid.version,carrier:'CJ대한통운',tracking:'123456789012'});assert.equal(shipped.fulfillment,'shipped');
 const g=fixture();g.payment.mode='live';const b=await g.started(),q=await g.service.acceptReturn(b.callback);g.remote.status='CANCELED';
 await assert.rejects(g.service.ship(b.id,{version:q.version,carrier:'CJ대한통운',tracking:'123456789012'}),{status:409});assert.equal((await g.repo.get(b.id)).fulfillment,'unfulfilled');
 g.remote.status='DONE';await assert.rejects(g.service.reconcile(b.id),{status:409});
});
test('an interrupted confirmation is canceled during recovery rather than approved again',async()=>{
 const f=fixture(),a=await f.started(),auth=f.payment.validateAuthentication(a.callback,a);
 await f.repo.patch(a,{state:'CONFIRMING',payment_auth_cipher:protect(secret).encrypt(auth)},'payment','payment_confirming');
 await assert.rejects(f.service.reconcile(a.id),{status:409});f.advance(61000);assert.equal((await f.service.reconcile(a.id)).state,'CANCELED');assert.equal(f.calls.filter(x=>x.action==='approve').length,0);
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

const business={kind:'tax_invoice',corp_num:'1234567891',corp_name:'검증용 상호',ceo_name:'검증 대표',address:'서울시 검증로 123',biz_type:'도소매',biz_class:'촬영장비',email:'test@example.invalid'};
function taxProvider(){const saved=new Map(),calls=[];return {mode:'test',calls,saved,async lookup(key){calls.push(['lookup',key]);return saved.get(key)||null;},async issue(key,row){calls.push(['issue',key]);const result={issued:true,approval_number:'202610081234567890123456',nts_status:'pending'};saved.set(key,result);return result;}};}
test('business tax fields validate registration checksum and email; provider-disabled requests are blocked',async()=>{
 assert.equal(evidenceFields(business).kind,'tax_invoice');
 for(const change of [{corp_num:'1234567890'},{corp_num:'0000000000'},{email:'wrong'},{ceo_name:'<script>'},{kind:'foreign'}])assert.throws(()=>evidenceFields({...business,...change}));
 const f=fixture();await assert.rejects(f.service.create(owner,'tax_request_disabled',{customer,items:[item],evidence:business}),{status:503});assert.equal(f.sql.prepare('SELECT COUNT(*) n FROM shop_orders').get().n,0);
});
test('tax invoice is queued atomically with paid state and issued once with a stable key',async()=>{
 const invoice=taxProvider(),f=fixture({invoice,evidence:business}),a=await f.started();const paid=await f.service.acceptReturn(a.callback);
 assert.equal(paid.state,'PAID');assert.equal(paid.document.status,'issued');assert.equal(invoice.calls.filter(x=>x[0]==='issue').length,1);assert.equal(invoice.calls[0][0],'lookup');assert.equal(invoice.calls[1][1],managementKey(a.id));
 await f.service.acceptReturn(a.callback);await f.documents.process(a.id);assert.equal(invoice.calls.filter(x=>x[0]==='issue').length,1);
 const raw=await f.repo.get(a.id);assert.ok(!raw.customer_cipher.includes(business.corp_num));assert.ok(!JSON.stringify(await f.service.list(owner)).includes(business.email));
});
test('missing outbox table rolls back paid state and compensates approval',async()=>{
 const f=fixture(),a=await f.started();f.sql.exec('DROP TABLE shop_documents');await assert.rejects(f.service.acceptReturn(a.callback));assert.notEqual((await f.repo.get(a.id)).state,'PAID');assert.equal(f.calls.filter(x=>x.action==='cancel').length,1);
});
test('document failure never cancels payment and durable retry survives a new service instance',async()=>{
 const invoice=taxProvider(),f=fixture({invoice,evidence:business}),a=await f.started();const issue=invoice.issue;invoice.issue=async()=>{throw Error('provider down');};
 const paid=await f.service.acceptReturn(a.callback);assert.equal(paid.state,'PAID');assert.equal(paid.document.status,'retry');assert.equal(f.calls.filter(x=>x.action==='cancel').length,0);
 invoice.issue=issue;f.advance(180000);const resumed=documentService({db:f.db,repo:f.repo,dataKey:secret,payment:f.payment,invoice,clock:f.clock});await resumed.drain();assert.equal((await resumed.get(a.id)).status,'issued');assert.equal(invoice.calls.filter(x=>x[0]==='issue').length,1);
});
test('lost invoice response is reconciled by the same document key without issuing twice',async()=>{
 const invoice=taxProvider(),original=invoice.issue;invoice.issue=async(...args)=>{await original(...args);throw Error('response lost');};const f=fixture({invoice,evidence:business}),a=await f.started();await f.service.acceptReturn(a.callback);
 f.advance(180000);await f.documents.process(a.id);assert.equal((await f.documents.get(a.id)).status,'issued');assert.equal(invoice.calls.filter(x=>x[0]==='issue').length,1);
});
test('concurrent workers claim one invoice; an expired lease can recover',async()=>{
 const invoice=taxProvider(),f=fixture({invoice,evidence:business}),a=await f.started();const process=f.documents.process;f.documents.process=async()=>null;await f.service.acceptReturn(a.callback);f.documents.process=process;
 await Promise.all([process(a.id),process(a.id)]);assert.equal(invoice.calls.filter(x=>x[0]==='issue').length,1);
});
test('unpaid or refunded orders and unexpected PG cash receipts cannot trigger a tax invoice',async()=>{
 for(const condition of ['cancel','cash','environment']){const invoice=taxProvider(),f=fixture({invoice,evidence:business}),a=await f.started();const process=f.documents.process;f.documents.process=async()=>null;await f.service.acceptReturn(a.callback);f.documents.process=process;
 if(condition==='cancel')f.remote.status='CANCELED';if(condition==='cash')f.remote.cashReceipt={issued:true};if(condition==='environment')invoice.mode='live';await process(a.id);assert.equal(invoice.calls.filter(x=>x[0]==='issue').length,0);assert.equal((await f.documents.get(a.id)).status,'review');}
});
test('cash receipt requires verified purpose, amount and approval; failures remain pending',async()=>{
 for(const purpose of ['income','business']){const f=fixture({evidence:{kind:'cash_receipt'}}),a=await f.started(),approve=f.payment.approve;f.payment.approve=async(...args)=>({...await approve(...args),cashReceipt:{issued:true,purpose,amount:24500,approvalNumber:'123456789',issuedAt:'20261008123456'}});const paid=await f.service.acceptReturn(a.callback);assert.equal(paid.document.status,'issued');assert.equal(paid.document.purpose,purpose);}
 const f=fixture({evidence:{kind:'cash_receipt'}}),a=await f.started();const paid=await f.service.acceptReturn(a.callback);assert.equal(paid.state,'PAID');assert.equal(paid.document.status,'retry');assert.equal(paid.document.approval_number,null);
});
test('tax invoice NTS transmission is refreshed without reissue and a later refund flags evidence',async()=>{
 const invoice=taxProvider(),f=fixture({invoice,evidence:business}),a=await f.started();await f.service.acceptReturn(a.callback);invoice.saved.get(managementKey(a.id)).nts_status='accepted';f.advance(301000);await f.documents.drain();assert.equal((await f.documents.get(a.id)).nts_status,'accepted');assert.equal(invoice.calls.filter(x=>x[0]==='issue').length,1);
 f.remote.status='CANCELED';await f.service.reconcile(a.id);assert.equal((await f.documents.get(a.id)).status,'review');assert.equal((await f.repo.get(a.id)).state,'CANCELED');
});
