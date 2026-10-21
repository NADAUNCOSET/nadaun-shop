const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const {DatabaseSync}=require('node:sqlite');
const {repository,orderService}=require('../../server/commerce/orders.cjs');
const {adminService}=require('../../server/commerce/admin.cjs');
const {toss}=require('../../server/commerce/toss.cjs');
const {endpoint}=require('../../server/commerce/http.cjs');
const {webhookEndpoint}=require('../../server/commerce/payment-webhook.cjs');
const {protect,hash,sessions}=require('../../server/commerce/security.cjs');
const key='ab'.repeat(32),owner=hash('lifecycle-customer');
function fixture(){
 let now=Date.parse('2026-10-21T03:00:00Z'),failAfterCancel=false,failBeforeCancel=false;
 const clock=()=>now,sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync('server/commerce/schema.sql','utf8'));
 const db={async batch(items){sql.exec('BEGIN');try{const rows=items.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return rows;}catch(e){sql.exec('ROLLBACK');throw e;}},async query(sql,p=[]){return(await this.batch([{sql,params:p}]))[0];}};
 const repo=repository(db,clock),remote=new Map(),cached=new Map(),calls=[];
 const payment=toss({SHOP_PAYMENT_MODE:'live',SHOP_TOSS_CLIENT_KEY:'live_ck_fixture',SHOP_TOSS_SECRET_KEY:'live_sk_fixture',SHOP_TOSS_MID:'fixture',SHOP_TOSS_LIVE_VERIFIED:'true'},async(url,opt)=>{
  const id=url.split('/')[5],value=remote.get(id);calls.push({url,method:opt.method,key:opt.headers['Idempotency-Key'],body:opt.body});
  if(opt.method==='POST'){
   if(failBeforeCancel)throw Error('timeout before processing');
   const operation=JSON.parse(opt.body),k=opt.headers['Idempotency-Key'];
   if(cached.has(k))return {ok:true,json:async()=>structuredClone(cached.get(k))};
   if(operation.refundableAmount!==value.balanceAmount)return {ok:false,json:async()=>({code:'BALANCE_MISMATCH'})};
   value.balanceAmount-=operation.cancelAmount;value.status=value.balanceAmount?'PARTIAL_CANCELED':'CANCELED';value.cancels.push({transactionKey:crypto.randomUUID(),cancelAmount:operation.cancelAmount,cancelStatus:'DONE',canceledAt:new Date(now).toISOString()});cached.set(k,structuredClone(value));
   if(failAfterCancel)throw Error('lost response after processing');
  }
  return {ok:true,json:async()=>structuredClone(value)};
 });
 const catalog={meta:{synced_at:new Date(now).toISOString()},redirects:{},products:[{id:'p',kind:'purchase',name:'테스트 상품',status:'sale',price:10000,offers:[{source:'smartstore'}],shipping_class:'standard'}]};
 const service=orderService({repo,catalog,detail:()=>({}),dataKey:key,payment,clock}),admin=adminService({db,service,dataKey:key,clock});
 async function create(paid=true){let order=await service.create(owner,'fixture-'+crypto.randomUUID(),{customer:{name:'가상 고객',phone:'01000000000',postcode:'01234',address:'가상 주소 123',address_detail:'가상 1층',consent:true},items:[{id:'p',option:'',quantity:1}]});if(!paid)return order;
  const row=await repo.get(order.id),paymentKey='payment_'+order.id,value={provider:'toss',mId:'fixture',paymentKey,orderId:order.id,totalAmount:row.total,balanceAmount:row.total,currency:'KRW',status:'DONE',isPartialCancelable:true,method:'카드',card:{approveNo:'1234'},approvedAt:new Date(now).toISOString(),cancels:[]};remote.set(paymentKey,value);
  await repo.patch(row,{state:'PAID',payment_mode:'live',payment_provider:'toss',payment_key:paymentKey,paid_at:now,payment_receipt_cipher:protect(key).encrypt(await payment.get(paymentKey))},'fixture','payment_done');return service.adminGet(order.id);
 }
 const input=(o,amount=o.total)=>({version:o.version,amount,reason:'고객 요청 취소',request_key:crypto.randomUUID(),confirmed:true});
 return {clock,sql,db,repo,service,admin,payment,calls,remote,create,input,advance:n=>now+=n,failAfter:v=>failAfterCancel=v,failBefore:v=>failBeforeCancel=v};
}
test('full refund is durable, exact, idempotent, private and exported with verified amounts',async()=>{
 const f=fixture(),o=await f.create(),input=f.input(o);let result=await f.service.refund(o.id,input,'admin');assert.equal(result.state,'CANCELED');assert.equal(result.payment_summary.canceled_amount,o.total);assert.equal(result.payment_summary.balance_amount,0);assert.equal(result.admin_refunds[0].status,'done');
 result=await f.service.refund(o.id,input,'admin');assert.equal(result.state,'CANCELED');assert.equal(f.calls.filter(c=>c.method==='POST').length,1);
 const pub=await f.service.get(o.id,owner);assert.ok(!JSON.stringify(pub).includes(input.request_key));assert.ok(!JSON.stringify(pub).includes('transactionKey'));assert.equal(pub.refund_pending,false);
 const csv=(await f.admin.export({format:'csv'})).body.toString();assert.match(csv,/토스취소확인액/);assert.match(csv,/14500/);
});
test('partial refunds retain a review hold and may be followed by remaining-balance cancellation',async()=>{
 const f=fixture(),o=await f.create();let r=await f.service.refund(o.id,f.input(o,5000),'admin');assert.equal(r.state,'PAYMENT_REVIEW');assert.equal(r.payment_summary.balance_amount,9500);assert.equal(r.payment_summary.canceled_amount,5000);
 await assert.rejects(f.service.ship(o.id,{version:r.version,carrier:'택배',tracking:'123456789'},'admin'),{status:409});
 r=await f.service.refund(o.id,f.input(r,9500),'admin');assert.equal(r.state,'CANCELED');assert.equal(r.payment_summary.cancellations.length,2);
});
test('refund rejects excess, non-integer, unsupported partial, missing confirmation and stale versions',async()=>{
 const f=fixture(),o=await f.create();for(const change of [{amount:o.total+1},{amount:1.2},{confirmed:false},{version:0},{reason:'a'}])await assert.rejects(f.service.refund(o.id,{...f.input(o),...change},'admin'));
 f.remote.values().next().value.isPartialCancelable=false;await assert.rejects(f.service.refund(o.id,f.input(o,1),'admin'),{status:409});assert.equal(f.calls.filter(c=>c.method==='POST').length,0);
});
test('concurrent different refund requests acquire one order lock before touching the provider',async()=>{
 const f=fixture(),o=await f.create(),r=await Promise.allSettled([f.service.refund(o.id,f.input(o,1000),'a'),f.service.refund(o.id,f.input(o,2000),'b')]);assert.equal(r.filter(x=>x.status==='fulfilled').length,1);assert.equal(f.calls.filter(c=>c.method==='POST').length,1);
});
test('lost refund response retries the same provider key without another cancellation',async()=>{
 const f=fixture(),o=await f.create(),input=f.input(o,3000);f.failAfter(true);await assert.rejects(f.service.refund(o.id,input,'admin'));let saved=await f.service.adminGet(o.id);assert.equal(saved.refund_pending,true);assert.equal((await f.admin.list({queue:'refund-review'})).summary.orders,1);
 await assert.rejects(f.service.refund(o.id,f.input(saved,3000),'admin'),{status:409});f.failAfter(false);
 saved=await f.service.refund(o.id,input,'admin');assert.equal(saved.payment_summary.canceled_amount,3000);const calls=f.calls.filter(c=>c.method==='POST');assert.equal(calls.length,2);assert.equal(calls[0].key,calls[1].key);assert.equal(calls[0].body,calls[1].body);assert.equal((await f.admin.list({queue:'refund-review'})).summary.orders,0);
});
test('stale idempotency keys cannot cause a fresh financial request after provider expiry',async()=>{
 const f=fixture(),o=await f.create(),input=f.input(o);f.failBefore(true);await assert.rejects(f.service.refund(o.id,input,'admin'));f.advance(14*86400000);f.failBefore(false);const before=f.calls.length;await assert.rejects(f.service.refund(o.id,input,'admin'),{status:409});assert.equal(f.calls.length,before);
});
test('audit failure before refund means no provider mutation; failure after refund can be recovered',async()=>{
 const f=fixture(),o=await f.create(),input=f.input(o);f.sql.exec("CREATE TRIGGER reject_refund BEFORE INSERT ON shop_order_events WHEN NEW.action='refund_requested' BEGIN SELECT RAISE(ABORT,'fixture'); END;");await assert.rejects(f.service.refund(o.id,input,'admin'));assert.equal(f.calls.filter(c=>c.method==='POST').length,0);
 f.sql.exec("DROP TRIGGER reject_refund; CREATE TRIGGER reject_complete BEFORE INSERT ON shop_order_events WHEN NEW.action='refund_completed' BEGIN SELECT RAISE(ABORT,'fixture'); END;");await assert.rejects(f.service.refund(o.id,input,'admin'));assert.equal((await f.service.adminGet(o.id)).refund_pending,true);f.sql.exec('DROP TRIGGER reject_complete');assert.equal((await f.service.refund(o.id,input,'admin')).state,'CANCELED');assert.equal(f.remote.values().next().value.cancels.length,1);
});
test('customer cancellation is ownership protected, holds shipping and may be resolved or refunded',async()=>{
 const f=fixture(),o=await f.create();await assert.rejects(f.service.customerCancel(o.id,'foreign',{version:o.version,reason:'취소 요청'}),{status:404});let r=await f.service.customerCancel(o.id,owner,{version:o.version,reason:'취소 요청'});assert.equal(r.state,'PAYMENT_REVIEW');assert.equal((await f.admin.list({queue:'cancel-requests'})).summary.orders,1);
 await f.service.paymentWebhook({eventType:'PAYMENT_STATUS_CHANGED',data:{orderId:o.id,paymentKey:'payment_'+o.id,status:'DONE'}});assert.equal((await f.service.adminGet(o.id)).state,'PAYMENT_REVIEW');
 r=await f.service.rejectCancellation(o.id,{version:r.version,reason:'고객 취소 요청 철회 확인'},'admin');assert.equal(r.state,'PAID');assert.equal((await f.admin.list({queue:'cancel-requests'})).summary.orders,0);
 r=await f.service.customerCancel(o.id,owner,{version:r.version,reason:'다시 취소 요청'});r=await f.service.refund(o.id,f.input(r),'admin');assert.equal(r.cancellation_request.status,'completed');
});
test('unpaid customer cancellation never accesses a payment provider',async()=>{
 const f=fixture(),o=await f.create(false),r=await f.service.customerCancel(o.id,owner,{version:0,reason:'미결제 취소'});assert.equal(r.state,'CANCELED');assert.equal(f.calls.length,0);
});
test('purchase confirmation is customer-only, delivery-gated, idempotent and independent of rewards',async()=>{
 const f=fixture();let o=await f.create();await assert.rejects(f.service.confirmPurchase(o.id,owner,{confirmed:true}),{status:409});
 o=await f.service.ship(o.id,{version:o.version,carrier:'검증택배',tracking:'123456789'},'admin');await assert.rejects(f.service.confirmPurchase(o.id,owner,{confirmed:true}),{status:409});o=await f.service.workflow(o.id,{version:o.version,stage:'delivered'},'admin');
 await assert.rejects(f.service.confirmPurchase(o.id,'other',{confirmed:true}),{status:404});await assert.rejects(f.service.confirmPurchase(o.id,owner,{}),{status:409});
 o=await f.service.confirmPurchase(o.id,owner,{confirmed:true});assert.equal(o.purchase_confirmation.confirmed_at,f.clock());await f.service.confirmPurchase(o.id,owner,{confirmed:true});assert.equal((await f.repo.events(o.id)).filter(e=>e.action==='purchase_confirmed').length,1);assert.equal((await f.admin.list({queue:'purchase-confirmed'})).summary.orders,1);
});
test('webhooks ignore unbound identities, trust only authenticated GET and never regress cancellation',async()=>{
 const f=fixture(),o=await f.create(),event={eventType:'PAYMENT_STATUS_CHANGED',data:{orderId:o.id,paymentKey:'payment_'+o.id,status:'CANCELED',totalAmount:1}};await f.service.paymentWebhook(event);assert.equal((await f.service.adminGet(o.id)).state,'PAID');
 const calls=f.calls.length;await f.service.paymentWebhook({...event,data:{...event.data,paymentKey:'foreign'}});assert.equal(f.calls.length,calls);
 const raw=await f.repo.get(o.id);await f.payment.cancel(raw,{id:'RF-'+crypto.randomUUID(),amount:raw.total,before_balance:raw.total,reason:'토스 관리자 취소'});await f.service.paymentWebhook({...event,data:{...event.data,status:'DONE'}});const after=await f.service.adminGet(o.id);assert.equal(after.state,'CANCELED');const v=after.version;await f.service.paymentWebhook(event);assert.equal((await f.service.adminGet(o.id)).version,v);
});
test('webhook route bounds payloads, hides errors and rejects unsupported methods',async()=>{
 const f=fixture(),handler=webhookEndpoint(()=>f),response=()=>({setHeader(){},status(n){this.code=n;return this;},json(v){this.body=v;return this;}});
 for(const [method,body,expected] of [['GET',{},405],['POST','x'.repeat(32769),413],['POST','invalid json',400],['POST',{eventType:'UNKNOWN'},200]]){const r=response();await handler({method,body,headers:{}},r);assert.equal(r.code,expected);}
});
test('financial endpoints require admin session and allowed origin; customer cannot refund',async()=>{
 const f=fixture(),o=await f.create(),handler=endpoint({service:f.service,repo:f.repo,adminService:f.admin,password:'unused',sessionKey:key,enabled:true,clock:f.clock});
 async function invoke(action,body,headers={}){const r={setHeader(){},status(n){this.code=n;return this;},json(v){this.body=v;return this;}};await handler({url:'/api/orders?action='+action,method:'POST',body,headers:{origin:'https://shop.nadaun.co',...headers}},r);return r;}
 const input={id:o.id,...f.input(o),actor:'forged'};assert.equal((await invoke('admin-refund',input)).code,401);const cookie='__Host-nadaun-admin='+sessions(key,f.clock).issue('owner','admin',1000);assert.equal((await invoke('admin-refund',input,{cookie,origin:'https://evil.invalid'})).code,403);assert.equal((await invoke('admin-refund',input,{cookie})).code,200);assert.equal((await f.repo.events(o.id)).at(-1).actor,'owner');
});
test('scheduled reconciliation is bounded, repeats safely and reports provider failures',async()=>{
 const f=fixture();await f.create();await f.create();await f.create();assert.equal((await f.service.paymentDrain()).processed,2);assert.equal((await f.service.paymentDrain()).processed,1);assert.equal((await f.service.paymentDrain()).processed,0);f.advance(900001);assert.equal((await f.service.paymentDrain()).processed,2);
});
test('public webhook shares the jobs function without exposing protected job execution',async()=>{
 const handler=require('../../api/commerce-jobs.js'),config=JSON.parse(fs.readFileSync('vercel.json','utf8'));
 assert.equal(fs.readdirSync('api').filter(n=>n.endsWith('.js')).length,12);
 assert.equal(config.routes.find(r=>r.src==='^/api/toss-webhook$').dest,'/api/commerce-jobs?action=toss-webhook');
 for(const [method,query,body,code] of [['GET',{action:'toss-webhook'},{},405],['POST',{action:'toss-webhook'},'x'.repeat(32769),413],['POST',{}, {},401],['POST',{action:'other'}, {},401]]){
  const r={setHeader(){},status(n){this.code=n;return this;},json(v){this.body=v;return this;}};
  await handler({method,query,body,headers:{}},r);assert.equal(r.code,code);
 }
});
