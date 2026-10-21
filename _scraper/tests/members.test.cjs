const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const {DatabaseSync}=require('node:sqlite');
const {memberService}=require('../../server/commerce/members.cjs');
const {repository,orderService}=require('../../server/commerce/orders.cjs');
const {memberEndpoint}=require('../../server/commerce/member-http.cjs');
const {endpoint}=require('../../server/commerce/http.cjs');
const {protect,sessions,passwordHash}=require('../../server/commerce/security.cjs');
const {context,MODE_COOKIE}=require('../../server/commerce/test-context.cjs');
const {database}=require('../../server/commerce/d1.cjs');
const {toss}=require('../../server/commerce/toss.cjs');
const key='ab'.repeat(32),password='a-long-private-member-password';
const signup=(email='first@example.com')=>({email,name:'테스트 회원',password,terms:true,privacy:true,age14:true});
function fixture({testing=true,bps=100}={}){
 let now=Date.now(),remote;const clock=()=>now,sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync('server/commerce/schema.sql','utf8'));
 const db={async batch(items){sql.exec('BEGIN');try{const rows=items.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return rows;}catch(e){sql.exec('ROLLBACK');throw e;}},async query(statement,params=[]){return(await this.batch([{sql:statement,params}]))[0];}};
 const repo=repository(db,clock),members=memberService({db,repo,dataKey:key,sessionKey:key,enabled:true,earnBasisPoints:bps,confirmOrder:(...args)=>service.confirmPurchase(...args),testing,clock});
 const catalog={meta:{synced_at:new Date(now).toISOString()},products:[{id:'purchase',name:'카메라',kind:'purchase',price:100000,status:'inquiry',offers:[{source:'smartstore'}]}],redirects:{}};
 const payment=toss({SHOP_PAYMENT_MODE:'test',SHOP_TOSS_CLIENT_KEY:'test_ck_fixture',SHOP_TOSS_SECRET_KEY:'test_sk_fixture'},async(url,opt)=>{
  if(url.endsWith('/confirm')){const auth=JSON.parse(opt.body);remote={...auth,totalAmount:auth.amount,currency:'KRW',mId:'sample',status:'DONE',card:{approveNo:'123456'},approvedAt:new Date(now).toISOString()};}
  if(url.endsWith('/cancel'))remote.status='CANCELED';return {ok:true,json:async()=>({...remote})};
 });
 const service=orderService({repo,catalog,detail:()=>({}),dataKey:key,payment,testing,clock});
 const customer={name:'테스트 구매자',phone:'010-0000-0000',postcode:'01234',address:'테스트 주소 123',address_detail:'1층',consent:true};
 const payload={customer,items:[{id:'purchase',option:'',quantity:1}]};
 async function join(email){const joined=await members.signup(signup(email));return {...joined,identity:await members.authenticate(joined.token)};}
 async function paid(member){let order=await service.create(member.owner,'order-test-'+crypto.randomUUID(),payload);order=await service.approve(order.id,{version:order.version,stock_confirmed:true});const prepared=await service.start(order.id,member.owner,order.quote_version);const token=new URL(prepared.request.successUrl).searchParams.get('token');order=await service.acceptReturn({token,paymentKey:'qa_payment_'+crypto.randomUUID(),orderId:order.id,amount:String(order.total)});return order;}
 return {sql,db,repo,members,service,catalog,payload,join,paid,clock,advance:n=>now+=n};
}
async function invoke(handler,action,{method='POST',body={},cookie='',origin='https://shop.nadaun.co'}={}){const res={headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.code=n;return this;},json(v){this.value=v;return this;}};await handler({method,url:'/api/members?action='+action,headers:{origin,cookie,'x-forwarded-for':'test-ip'},body},res);return res;}
test('signup encrypts identity and hashes password/recovery; consent and normalized duplicate checks',async()=>{
 const f=fixture();await assert.rejects(f.members.signup({...signup(),privacy:false}),{status:400});await assert.rejects(f.members.signup({...signup(),password:'short'}),{status:400});
 const a=await f.join(),raw=f.sql.prepare('SELECT * FROM shop_members').get();assert.equal(raw.email_hash.includes('@'),false);assert.equal(raw.profile_cipher.includes('example'),false);assert.equal(raw.password_hash.includes(password),false);assert.equal(raw.recovery_hash.includes(a.recovery_code),false);assert.equal(a.member.email_verified,false);
 await assert.rejects(f.members.signup(signup(' FIRST@example.com ')),{status:409});assert.equal(f.sql.prepare('SELECT COUNT(*) AS n FROM shop_members').get().n,1);
});
test('login uses persistent revocable sessions and rejects wrong or expired tokens',async()=>{
 const f=fixture(),a=await f.join();await assert.rejects(f.members.login({email:'first@example.com',password:'wrong-password'}),{status:401});await assert.rejects(f.members.login({email:'missing@example.com',password}),{status:401});assert.equal(await f.members.authenticate('invalid'),null);await f.members.logout(a.token);assert.equal(await f.members.authenticate(a.token),null);
 const b=await f.members.login({email:'FIRST@example.com',password});f.advance(8*86400000);assert.equal(await f.members.authenticate(b.token),null);
});
test('password change and one-use recovery revoke all old sessions; old recovery cannot be reused',async()=>{
 const f=fixture(),a=await f.join(),b=await f.members.login({email:a.member.email,password});const changed=await f.members.changePassword(a.identity,{current_password:password,password:password+'-new'});assert.equal(await f.members.authenticate(a.token),null);assert.equal(await f.members.authenticate(b.token),null);
 await assert.rejects(f.members.recover({email:a.member.email,recovery_code:a.recovery_code,password}),{status:401});await f.members.recover({email:a.member.email,recovery_code:changed.recovery_code,password});await assert.rejects(f.members.recover({email:a.member.email,recovery_code:changed.recovery_code,password}),{status:401});assert.ok((await f.members.login({email:a.member.email,password})).token);
});
test('member orders follow account across browsers without linking another guest or account by email',async()=>{
 const f=fixture(),a=await f.join(),b=await f.join('second@example.com'),order=await f.service.create(a.identity.owner,'request-membership-fixture',f.payload),again=await f.members.login({email:a.member.email,password}),identity=await f.members.authenticate(again.token);
 assert.equal((await f.service.get(order.id,identity.owner)).id,order.id);await assert.rejects(f.service.get(order.id,b.identity.owner),{status:404});assert.deepEqual(await f.service.list(b.identity.owner),[]);
 const handler=endpoint({service:f.service,repo:f.repo,members:f.members,sessionKey:key,password:'not-used',enabled:true});let r=await invoke(handler,'orders',{method:'GET',cookie:'__Host-nadaun-member='+again.token});assert.equal(r.code,200);assert.equal(r.value.orders.length,1);r=await invoke(handler,'session',{cookie:'__Host-nadaun-member='+again.token});assert.equal(r.headers['Set-Cookie'],undefined);
});
test('CSRF, anonymous points administration and forged admin sessions fail closed',async()=>{
 const f=fixture(),handler=memberEndpoint({members:f.members,repo:f.repo,sessionKey:key});assert.equal((await invoke(handler,'signup',{body:signup(),origin:'https://evil.example'})).code,403);assert.equal((await invoke(handler,'admin-members',{method:'GET'})).code,401);assert.equal((await invoke(handler,'admin-points',{body:{amount:100},cookie:'__Host-nadaun-admin=fake'})).code,401);assert.equal((await invoke(handler,'me',{method:'GET'})).value.authenticated,false);
 const r=await invoke(handler,'signup',{body:signup()});assert.equal(r.code,201);assert.match(r.headers['Set-Cookie'],/Secure; HttpOnly; SameSite=Lax/);assert.equal('token' in r.value,false);
});
test('point adjustments are atomic, idempotent, reasoned and cannot make a manual negative balance',async()=>{
 const f=fixture(),a=await f.join(),input={id:a.member.id,amount:1000,reason:'테스트 지급',request_key:crypto.randomUUID()};await f.members.adjust(input,'owner');await f.members.adjust(input,'owner');assert.equal((await f.members.me(a.identity)).points.balance,1000);await assert.rejects(f.members.adjust({...input,amount:2000},'owner'),{status:409});await assert.rejects(f.members.adjust({...input,amount:-1001,request_key:crypto.randomUUID()},'owner'),{status:409});assert.equal((await f.members.me(a.identity)).points.balance,1000);
});
test('complete member purchase, simulated provider approval, admin visibility, purchase reward and refund reversal',async()=>{
 const f=fixture(),a=await f.join(),order=await f.paid(a.identity);assert.equal(order.state,'PAID');assert.equal(order.payment_mode,'test');assert.equal((await f.service.adminGet(order.id)).customer.name,f.payload.customer.name);await assert.rejects(f.members.confirm(a.identity,{id:order.id}),{status:409});
 const delivered=await f.service.qaDeliver(order.id,{version:order.version},'owner');assert.equal(delivered.shipments[0].delivery_status,'delivered');await f.members.confirm(a.identity,{id:order.id});await f.members.confirm(a.identity,{id:order.id});assert.equal((await f.members.me(a.identity)).points.balance,1000);
 let canceled=await f.service.qaCancel(order.id,{version:(await f.service.adminGet(order.id)).version},'owner');assert.equal(canceled.state,'CANCELED');assert.equal((await f.members.me(a.identity)).points.balance,0);canceled=await f.service.qaCancel(order.id,{version:canceled.version},'owner');assert.equal((await f.members.me(a.identity)).points.history.length,2);
});
test('test orders cannot earn real rewards or simulate shipping in the operational service',async()=>{
 const f=fixture({testing:false}),a=await f.join(),order=await f.paid(a.identity);await assert.rejects(f.service.qaDeliver(order.id,{version:order.version},'owner'),{status:404});await assert.rejects(f.service.qaCancel(order.id,{version:order.version},'owner'),{status:404});await assert.rejects(f.members.confirm(a.identity,{id:order.id}),{status:409});assert.equal((await f.members.me(a.identity)).points.balance,0);
});
test('unapproved points policy cannot award points and never advertises redemption',async()=>{
 const f=fixture({bps:0}),a=await f.join();assert.equal(f.members.policy().earn_enabled,false);assert.equal(f.members.policy().redemption_enabled,false);await assert.rejects(f.members.confirm(a.identity,{id:'missing'}),{status:409});
});
test('withdrawal erases account profile and login while preserving audit references',async()=>{
 const f=fixture(),a=await f.join();await f.members.close(a.identity,{password,confirmed:true});assert.equal(await f.members.authenticate(a.token),null);const row=f.sql.prepare('SELECT * FROM shop_members').get();assert.equal(row.status,'closed');assert.equal(protect(key).decrypt(row.profile_cipher).email,'');await assert.rejects(f.members.login({email:'first@example.com',password}),{status:401});
});
test('test mode needs a signed limited cookie and uses distinct keys, cookie names and SQL namespace',async()=>{
 const env={SHOP_SESSION_KEY:key,SHOP_ORDER_DATA_KEY:'cd'.repeat(32),SHOP_QA_ENABLED:'true',SHOP_ORDERS_ENABLED:'false',SHOP_TOSS_CLIENT_KEY:'live_ck_do_not_use',SHOP_TOSS_SECRET_KEY:'live_sk_do_not_use',SHOP_QA_TOSS_CLIENT_KEY:'test_ck_sample',SHOP_QA_TOSS_SECRET_KEY:'test_sk_sample'};
 const req=value=>({headers:{cookie:MODE_COOKIE+'='+value}});assert.equal(context(req('fake'),env).testing,false);const token=sessions(key).issue('storefront-qa','storefront-qa',3600),c=context(req(token),env);assert.equal(c.testing,true);assert.equal(c.cookiePrefix,'nadaun-qa');assert.notEqual(c.env.SHOP_SESSION_KEY,key);assert.notEqual(c.env.SHOP_ORDER_DATA_KEY,env.SHOP_ORDER_DATA_KEY);assert.equal(c.env.SHOP_TOSS_CLIENT_KEY,'test_ck_sample');assert.equal(context(req(token),{...env,SHOP_QA_ENABLED:'false'}).testing,false);
 let sent;const db=database({...c.env,SHOP_CF_ACCOUNT_ID:'a'.repeat(32),SHOP_D1_DATABASE_ID:'a'.repeat(36),SHOP_D1_API_TOKEN:'fixture'},async(u,o)=>{sent=JSON.parse(o.body);return {ok:true,json:async()=>({success:true,result:[{success:true,results:[]}]})};});await db.query('SELECT * FROM shop_orders JOIN shop_members ON 1=1');assert.match(sent.batch[0].sql,/qa_shop_orders JOIN qa_shop_members/);
});
