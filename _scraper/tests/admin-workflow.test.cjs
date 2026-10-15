const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {DatabaseSync}=require('node:sqlite');
const {repository,orderService}=require('../../server/commerce/orders.cjs');
const {adminService,filters}=require('../../server/commerce/admin.cjs');
const {endpoint}=require('../../server/commerce/http.cjs');
const {protect,sessions,passwordHash,hash}=require('../../server/commerce/security.cjs');
const secret='cd'.repeat(32),owner=hash('workflow-customer'),actor='operator@example.invalid';
const customer={name:'테스트 고객',phone:'010-0000-0000',postcode:'01234',address:'테스트 주소',address_detail:'검증용',consent:true};
function fixture(){
 let now=Date.parse('2026-10-15T03:00:00Z');const clock=()=>now;
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync('server/commerce/schema.sql','utf8'));
 const db={async batch(statements){sql.exec('BEGIN');try{const out=statements.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return out;}catch(error){sql.exec('ROLLBACK');throw error;}},async query(s,p=[]){return (await this.batch([{sql:s,params:p}]))[0];}};
 const catalog={meta:{synced_at:new Date(now).toISOString(),revision:'workflow-fixture'},redirects:{},products:[{id:'purchase',kind:'purchase',name:'검증 구매',status:'sale',price:10000,shipping_class:'standard',offers:[{source:'smartstore'}]},{id:'rental',kind:'rental',name:'검증 렌탈',status:'sale'}]};
 const detail=()=>({rental:{rates:[{label:'24시간',price:10000}]}}),calls=[];
 const payment={mode:'live',prepare(row){calls.push('prepare');return {id:row.id};},async get(key){calls.push('get');const row=(await db.query('SELECT * FROM shop_orders WHERE payment_key=?',[key]))[0];return {provider:'inicis',orderId:row.id,paymentKey:key,totalAmount:row.total,currency:'KRW',status:'DONE'};}};
 const repo=repository(db,clock),service=orderService({repo,catalog,detail,dataKey:secret,sessionKey:secret,payment,clock}),admin=adminService({db,service,dataKey:secret,clock});
 let key=0;
 const create=()=>service.create(owner,'workflow_request_'+String(++key).padStart(5,'0'),{customer,items:[{id:'purchase',option:'',quantity:1}]});
 const rental=()=>service.createRental(owner,'workflow_request_'+String(++key).padStart(5,'0'),{customer,rental:{start_date:'2026-10-16',end_date:'2026-10-17',pickup_time:'12:00',return_time:'12:00'},items:[{id:'rental',option:'24시간',quantity:1}]});
 async function paid(order,fulfillment='unfulfilled',mode='live'){const row=await repo.get(order.id);await repo.patch(row,{state:'PAID',payment_mode:mode,payment_provider:'inicis',payment_key:'workflow_payment_'+row.id,fulfillment,total:14500},'fixture','fixture_paid');return service.adminGet(row.id);}
 return {sql,db,repo,service,admin,clock,create,rental,paid,calls,advance:ms=>now+=ms};
}
function request(handler,action,method='GET',body,headers={}){
 const res={headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.code=n;return this;},json(v){this.body=v;return this;},send(v){this.body=v;return this;}};
 return handler({url:'/api/orders?action='+action,method,body,headers:{origin:'https://shop.nadaun.co','x-forwarded-for':'127.0.0.1',...headers}},res).then(()=>res);
}
test('configured admin email and password are both required; config never reveals the account',async()=>{
 const f=fixture(),password=await passwordHash('workflow-only administrator password'),handler=endpoint({service:f.service,repo:f.repo,adminService:f.admin,password,email:'  Operator@Example.Invalid ',sessionKey:secret,enabled:false,clock:f.clock});
 const config=await request(handler,'config');assert.equal(config.body.adminLoginRequiresEmail,true);assert.ok(!JSON.stringify(config.body).includes('operator'));
 for(const body of [{password:'workflow-only administrator password'},{email:'someone@example.invalid',password:'workflow-only administrator password'},{email:actor,password:'wrong password'}]){const res=await request(handler,'login','POST',body);assert.equal(res.code,401);assert.equal(res.body.error,'로그인 정보를 확인해주세요.');}
 const logged=await request(handler,'login','POST',{email:' OPERATOR@EXAMPLE.INVALID ',password:'workflow-only administrator password'});assert.equal(logged.code,200);
 const cookie=logged.headers['Set-Cookie'].split(';')[0];assert.equal(sessions(secret,f.clock).read(cookie.slice(cookie.indexOf('=')+1),'admin'),actor);
 for(const token of [sessions(secret,f.clock).issue('owner','admin',3600),sessions(secret,f.clock).issue(actor,'customer',3600),'forged'])assert.equal((await request(handler,'admin-orders','GET',null,{cookie:'__Host-nadaun-admin='+token})).code,401);
 assert.equal((await request(handler,'admin-orders','GET',null,{cookie})).code,200);
 f.advance(8*3600000+1);assert.equal((await request(handler,'admin-orders','GET',null,{cookie})).code,401);
 assert.throws(()=>endpoint({service:f.service,repo:f.repo,password,email:'not-an-email',sessionKey:secret}),{status:503});
});
test('email-enabled login retains rate limiting and cross-origin rejection',async()=>{
 const f=fixture(),password=await passwordHash('workflow-only administrator password'),handler=endpoint({service:f.service,repo:f.repo,adminService:f.admin,password,email:actor,sessionKey:secret,clock:f.clock});
 for(let i=0;i<10;i++)assert.equal((await request(handler,'login','POST',{email:actor,password:'wrong'})).code,401);
 assert.equal((await request(handler,'login','POST',{email:actor,password:'workflow-only administrator password'})).code,429);
 assert.equal((await request(handler,'login','POST',{email:actor,password:'workflow-only administrator password'},{origin:'https://other.invalid'})).code,403);
});
test('internal notes persist encrypted, stay out of customer responses, and audit the session actor',async()=>{
 const f=fixture(),order=await f.create(),handler=endpoint({service:f.service,repo:f.repo,adminService:f.admin,password:'unused',email:actor,sessionKey:secret,clock:f.clock}),cookie='__Host-nadaun-admin='+sessions(secret,f.clock).issue(actor,'admin',3600);
 assert.equal((await request(handler,'admin-note','POST',{id:order.id,version:0,note:'내부 상담 내용'})).code,401);
 const saved=await request(handler,'admin-note','POST',{id:order.id,version:0,note:'  내부 상담 내용\n추가 검수  ',actor:'forged-owner'},{cookie});assert.equal(saved.code,200);assert.deepEqual(saved.body.order.admin_note,{text:'내부 상담 내용\n추가 검수',updated_at:f.clock(),actor});
 const row=await f.repo.get(order.id);assert.ok(!row.customer_cipher.includes('내부 상담'));assert.equal(protect(secret).decrypt(row.customer_cipher)._admin_note.actor,actor);
 const publicOrder=await f.service.get(order.id,owner);assert.ok(!('admin_note' in publicOrder));assert.ok(!JSON.stringify(publicOrder).includes('내부 상담'));assert.ok(!('_admin_note' in saved.body.order.customer));
 const events=await f.repo.events(order.id);assert.equal(events.at(-1).actor,actor);assert.equal(events.at(-1).action,'admin_note_updated');assert.ok(!JSON.stringify(events).includes('내부 상담'));
 const cleared=await f.service.saveNote(order.id,{version:1,note:''},actor);assert.equal(cleared.admin_note.text,'');assert.equal((await f.repo.events(order.id)).at(-1).action,'admin_note_cleared');
});
test('note validation and optimistic concurrency preserve the winning update and audit transaction',async()=>{
 const f=fixture(),order=await f.create();
 for(const note of [null,{},'x'.repeat(2001),'bad\u0000text'])await assert.rejects(f.service.saveNote(order.id,{version:0,note},actor),{status:400});
 const result=await Promise.allSettled(['first','second'].map(note=>f.service.saveNote(order.id,{version:0,note},actor)));assert.equal(result.filter(r=>r.status==='fulfilled').length,1);assert.equal((await f.repo.events(order.id)).length,2);
 await assert.rejects(f.service.saveNote(order.id,{version:0,note:'stale'},actor),{status:409});
 const before=await f.repo.get(order.id);f.sql.exec("CREATE TRIGGER reject_audit BEFORE INSERT ON shop_order_events BEGIN SELECT RAISE(ABORT,'audit unavailable'); END;");
 await assert.rejects(f.service.saveNote(order.id,{version:1,note:'must roll back'},actor));assert.equal((await f.repo.get(order.id)).customer_cipher,before.customer_cipher);assert.equal((await f.repo.get(order.id)).version,1);
});
test('notes are blocked during payment so they cannot race PG approval persistence',async()=>{
 for(const state of ['PAYMENT_PENDING','CONFIRMING']){const f=fixture(),order=await f.create();await f.repo.patch(await f.repo.get(order.id),{state},'fixture','state_fixture');await assert.rejects(f.service.saveNote(order.id,{version:1,note:'pending'},actor),{status:409});assert.equal((await f.repo.get(order.id)).version,1);assert.equal(f.calls.length,0);}
});
test('unpaid requested and approved cancellation records a private reason without refunding',async()=>{
 for(const approve of [false,true]){const f=fixture();let order=await f.create();if(approve)order=await f.service.approve(order.id,{version:0,stock_confirmed:true},actor);
  const canceled=await f.service.cancelRequest(order.id,{version:order.version,reason:'공급 재고 미확보'},actor);assert.equal(canceled.state,'CANCELED');assert.equal(canceled.quote_expires,null);assert.deepEqual(canceled.admin_cancellation,{reason:'공급 재고 미확보',created_at:f.clock(),actor});
  const raw=await f.repo.get(order.id);assert.ok(!raw.customer_cipher.includes('재고'));assert.equal(protect(secret).decrypt(raw.customer_cipher)._admin_cancellation.reason,'공급 재고 미확보');assert.equal(raw.payment_key,null);assert.equal(f.calls.length,0);
  const events=await f.repo.events(order.id);assert.equal(events.at(-1).action,'request_canceled');assert.equal(events.at(-1).actor,actor);assert.ok(!JSON.stringify(events).includes('재고'));assert.ok(!JSON.stringify(await f.service.get(order.id,owner)).includes('미확보'));
  await assert.rejects(f.service.cancelRequest(order.id,{version:canceled.version,reason:'중복 취소'},actor),{status:409});
 }
});
test('cancel requires a current version and reason and rejects any payment or fulfillment evidence',async()=>{
 const f=fixture(),order=await f.create();
 for(const reason of ['',null,'x','x'.repeat(501),'bad\u0000reason'])await assert.rejects(f.service.cancelRequest(order.id,{version:0,reason},actor),{status:400});
 await assert.rejects(f.service.cancelRequest(order.id,{version:99,reason:'사유 입력'},actor),{status:409});
 for(const [key,value] of [['state','PAYMENT_PENDING'],['state','CONFIRMING'],['state','PAID'],['state','PAYMENT_REVIEW'],['fulfillment','processing'],['fulfillment','shipped'],['carrier','택배사'],['tracking','1234567'],['payment_key','pg-fixture'],['payment_mode','test'],['payment_provider','inicis'],['payment_auth_cipher','auth-fixture'],['payment_receipt_cipher','receipt-fixture'],['paid_at',f.clock()]]){
  const g=fixture(),fresh=await g.create();await g.repo.patch(await g.repo.get(fresh.id),{[key]:value},'fixture','evidence_fixture');await assert.rejects(g.service.cancelRequest(fresh.id,{version:1,reason:'취소 시험'},actor),{status:409});assert.equal((await g.repo.get(fresh.id)).version,1);assert.equal(g.calls.length,0);
 }
});
test('cancel versus payment start has exactly one winner and never overwrites an active payment',async()=>{
 const f=fixture(),requested=await f.create(),order=await f.service.approve(requested.id,{version:0,stock_confirmed:true},actor);
 const result=await Promise.allSettled([f.service.cancelRequest(order.id,{version:order.version,reason:'고객 접수 철회'},actor),f.service.start(order.id,owner,order.quote_version)]);assert.equal(result.filter(r=>r.status==='fulfilled').length,1);
 const row=await f.repo.get(order.id);assert.ok(['CANCELED','PAYMENT_PENDING'].includes(row.state));assert.equal((await f.repo.events(order.id)).length,3);if(row.state==='CANCELED')assert.equal(f.calls.length,0);
});
test('order kinds, action queues and exports distinguish sales from rental pickup and return',async()=>{
 const f=fixture(),purchase=await f.paid(await f.create()),pickup=await f.paid(await f.rental()),returning=await f.paid(await f.rental(),'processing');await f.paid(await f.rental(),'shipped');await f.paid(await f.rental(),'unfulfilled','test');await f.create();
 const all=await f.admin.list({});assert.equal(all.summary.orders,5);assert.equal(all.summary.toShip,1);assert.equal(all.summary.rentalPickup,1);assert.equal(all.summary.rentalReturn,1);assert.deepEqual(all.workload,all.summary);
 for(const [queue,id] of [['purchase-shipping',purchase.id],['rental-pickup',pickup.id],['rental-return',returning.id]]){const list=await f.admin.list({queue});assert.deepEqual(list.orders.map(o=>o.id),[id]);assert.equal(list.summary.orders,1);assert.equal(list.workload.orders,5);const csv=(await f.admin.export({queue,format:'csv'})).body.toString();assert.equal(csv.trim().split('\r\n').length,2);assert.ok(csv.includes(id));}
 assert.equal((await f.admin.list({kind:'rental'})).summary.orders,3);assert.equal((await f.admin.list({kind:'purchase'})).summary.orders,2);assert.equal((await f.admin.list({kind:'rental',mode:'test'})).summary.orders,1);
 assert.equal((await f.admin.list({queue:'rental-pickup',search:pickup.id})).workload.orders,1);
 for(const input of [{kind:'invalid'},{queue:'unpaid-pickup'},{queue:"' OR 1=1"}])assert.throws(()=>filters(input,f.clock),{status:400});
});
test('authenticated actor is recorded on approval, rental handover, return and shipping',async()=>{
 const f=fixture(),purchase=await f.create();await f.service.approve(purchase.id,{version:0,stock_confirmed:true},actor);assert.equal((await f.repo.events(purchase.id)).at(-1).actor,actor);
 const paid=await f.paid(await f.service.adminGet(purchase.id));await f.service.ship(paid.id,{version:paid.version,carrier:'검증택배',tracking:'123456789'},actor);assert.equal((await f.repo.events(paid.id)).at(-1).actor,actor);
 const rent=await f.paid(await f.rental()),picked=await f.service.pickup(rent.id,{version:rent.version},actor);await f.service.rentalReturn(rent.id,{version:picked.version},actor);assert.deepEqual((await f.repo.events(rent.id)).slice(-2).map(e=>e.actor),[actor,actor]);
});
test('payment review queue matches its counter across confirming and review states',async()=>{
 const f=fixture();
 for(const state of ['CONFIRMING','PAYMENT_REVIEW','PAYMENT_PENDING']){const order=await f.create();await f.repo.patch(await f.repo.get(order.id),{state},'fixture','state_fixture');}
 const all=await f.admin.list({}),review=await f.admin.list({queue:'payment-review'});assert.equal(all.summary.paymentReview,2);assert.equal(review.summary.orders,2);assert.equal(review.workload.orders,3);assert.deepEqual(new Set(review.orders.map(o=>o.state)),new Set(['CONFIRMING','PAYMENT_REVIEW']));
});
test('request cancellation endpoint requires admin origin and records only its session identity',async()=>{
 const f=fixture(),order=await f.create(),handler=endpoint({service:f.service,repo:f.repo,adminService:f.admin,password:'unused',email:actor,sessionKey:secret,enabled:false,clock:f.clock}),cookie='__Host-nadaun-admin='+sessions(secret,f.clock).issue(actor,'admin',3600),body={id:order.id,version:0,reason:'고객 접수 철회',actor:'forged-owner'};
 assert.equal((await request(handler,'admin-cancel-request','POST',body)).code,401);
 assert.equal((await request(handler,'admin-cancel-request','POST',body,{cookie,origin:'https://evil.invalid'})).code,403);
 const canceled=await request(handler,'admin-cancel-request','POST',body,{cookie,origin:'https://order.nadaun.co'});assert.equal(canceled.code,200);assert.equal(canceled.body.order.admin_cancellation.actor,actor);assert.equal((await f.repo.events(order.id)).at(-1).actor,actor);
});
test('private notes and cancellation reasons export as inert text and preserve customer separation',async()=>{
 const f=fixture(),order=await f.create(),noted=await f.service.saveNote(order.id,{version:0,note:'=SUM(1,2)'},actor);await f.service.cancelRequest(order.id,{version:noted.version,reason:'@private internal reason'},actor);
 const csv=(await f.admin.export({format:'csv'})).body.toString();assert.ok(csv.includes("'=SUM(1,2)"));assert.ok(csv.includes("'@private internal reason"));
 const ExcelJS=require('exceljs'),book=new ExcelJS.Workbook();await book.xlsx.load((await f.admin.export({format:'xlsx'})).body);const sheet=book.getWorksheet('주문결제'),headers=sheet.getRow(1).values;
 for(const name of ['내부 메모','접수 취소 사유'])assert.equal(sheet.getRow(2).getCell(headers.indexOf(name)).type,ExcelJS.ValueType.String);
 assert.ok(!JSON.stringify(await f.service.get(order.id,owner)).includes('private internal'));
});
test('rental maximum is exactly fourteen elapsed KST days including month and year boundaries',()=>{
 const {rentalSchedule}=require('../../server/commerce/rental.cjs'),f=fixture();
 for(const [start,end] of [['2026-10-16','2026-10-30'],['2026-10-25','2026-11-08'],['2026-12-25','2027-01-08']]){
  const raw={start_date:start,end_date:end,pickup_time:'12:15',return_time:'12:15'},value=rentalSchedule(raw,f.clock);assert.equal(value.return_at-value.pickup_at,14*86400000);
  const before=rentalSchedule({...raw,return_time:'12:14'},f.clock);assert.equal(before.return_at-before.pickup_at,14*86400000-60000);
  assert.throws(()=>rentalSchedule({...raw,return_time:'12:16'},f.clock),{status:400,message:'최대 대여기간은 2주(14일)입니다. 수령·반납 방문 일시를 확인해주세요.'});
 }
});
test('rental creation and approval cannot bypass the fourteen-day maximum',async()=>{
 const f=fixture(),rental={start_date:'2026-10-16',end_date:'2026-10-31',pickup_time:'12:00',return_time:'12:00'},input={customer,rental,items:[{id:'rental',option:'24시간',quantity:1}]};
 await assert.rejects(f.service.createRental(owner,'rental_too_long_request',input),{status:400});assert.equal((await f.repo.list()).length,0);
 const order=await f.rental(),row=await f.repo.get(order.id),stored=protect(secret).decrypt(row.customer_cipher);stored.rental={...stored.rental,...rental};await f.repo.patch(row,{customer_cipher:protect(secret).encrypt(stored)},'fixture','legacy_long_schedule');
 await assert.rejects(f.service.approve(order.id,{version:1,stock_confirmed:true,rental_prices:[{id:'rental',option:'24시간',unit_price:10000}]},actor),{status:400});assert.equal((await f.repo.get(order.id)).state,'REQUESTED');assert.equal(f.calls.length,0);
});
