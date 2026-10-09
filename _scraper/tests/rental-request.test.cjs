const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {DatabaseSync}=require('node:sqlite');
const {rentalSchedule,rentalQuote,rentalCustomer}=require('../../server/commerce/rental.cjs');
const {repository,orderService}=require('../../server/commerce/orders.cjs');
const {adminService}=require('../../server/commerce/admin.cjs');
const {protect,hash,sessions,passwordHash}=require('../../server/commerce/security.cjs');
const {endpoint}=require('../../server/commerce/http.cjs');
const secret='ab'.repeat(32),owner=hash('rental-test-owner'),clock=()=>Date.parse('2026-10-09T00:00:00Z');
const schedule={start_date:'2026-10-10',end_date:'2026-10-11',pickup_time:'09:15',return_time:'10:45'};
const input={customer:{name:'검증 예약자',phone:'010-0000-0000',consent:true},items:[{id:'r1',option:'24시간',quantity:2}],rental:schedule};
function fixture(){
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync('server/commerce/schema.sql','utf8'));
 const db={async batch(statements){sql.exec('BEGIN');try{const result=statements.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return result;}catch(e){sql.exec('ROLLBACK');throw e;}},async query(sql,params=[]){return (await this.batch([{sql,params}]))[0];}};
 const catalog={meta:{synced_at:new Date(clock()).toISOString(),revision:'rental-test'},redirects:{old:'r1'},products:[{id:'r1',kind:'rental',name:'검증용 조명',status:'sale',image:'/test.jpg'},{id:'purchase',kind:'purchase',name:'판매 상품',status:'sale'}]};
 const detail=()=>({rental:{rates:[{label:'12시간',price:10000},{label:'24시간',price:20000}]}});
 const repo=repository(db,clock),service=orderService({repo,catalog,detail,dataKey:secret,clock}),admin=adminService({db,service,dataKey:secret,clock});return {sql,db,catalog,detail,repo,service,admin};
}
test('rental schedule records exact minute and KST dates including year boundaries',()=>{
 const s=rentalSchedule(schedule,clock);assert.equal(s.pickup_at,Date.parse('2026-10-10T00:15:00Z'));assert.equal(s.return_at,Date.parse('2026-10-11T01:45:00Z'));
 const next=rentalSchedule({start_date:'2026-12-31',end_date:'2027-01-01',pickup_time:'23:59',return_time:'00:01'},clock);assert.equal(next.return_at-next.pickup_at,120000);
 assert.equal(rentalSchedule({...schedule,end_date: schedule.start_date,return_time:'09:16'},clock).return_at-rentalSchedule(schedule,clock).pickup_at,60000);
});
test('impossible dates, reversed visits, past visits and invalid time values fail',()=>{
 for(const value of [{...schedule,start_date:'2026-02-30'},{...schedule,end_date:'2026-10-09'},{...schedule,end_date:schedule.start_date,return_time:schedule.pickup_time},{...schedule,pickup_time:'24:00'},{...schedule,return_time:'10:60'},{...schedule,start_date:'2026-10-08'}])assert.throws(()=>rentalSchedule(value,clock),{status:400});
 assert.throws(()=>rentalCustomer({...input.customer,consent:false}),{status:400});
});
test('displayed period rates and client-supplied total never become a full-period quote',()=>{
 const f=fixture(),q=rentalQuote(f.catalog,f.detail,input.items,null,clock);assert.equal(q.total,null);assert.equal(q.lines[0].unit_price,null);assert.equal(q.shipping,0);
 const confirmed=rentalQuote(f.catalog,f.detail,input.items,[{id:'r1',option:'24시간',unit_price:45000}],clock);assert.equal(confirmed.total,90000);assert.equal(confirmed.shipping,0);
 for(const prices of [[],[{id:'wrong',option:'24시간',unit_price:100}],[{id:'r1',option:'24시간',unit_price:1.5}],[{id:'r1',option:'24시간',unit_price:0}]])assert.throws(()=>rentalQuote(f.catalog,f.detail,input.items,prices,clock));
});
test('rental requests reject sold-out gear, sale products, unknown configurations and duplicate canonical IDs',()=>{
 const f=fixture();for(const rows of [[{id:'purchase',option:'',quantity:1}],[{id:'r1',option:'unknown',quantity:1}],[...input.items,{...input.items[0],id:'old'}],[{...input.items[0],quantity:100}]])assert.throws(()=>rentalQuote(f.catalog,f.detail,rows,null,clock));
 f.catalog.products[0].status='soldout';assert.throws(()=>rentalQuote(f.catalog,f.detail,input.items,null,clock),{status:409});
});
test('rental dates persist encrypted with one idempotent request and are visible only to the owner and admin',async()=>{
 const f=fixture(),a=await f.service.createRental(owner,'rental_request_key_001',{...input,total:1}),b=await f.service.createRental(owner,'rental_request_key_001',input);assert.equal(a.id,b.id);assert.equal(a.kind,'rental');assert.equal(a.total,null);assert.equal(a.rental.pickup_time,'09:15');assert.ok(!('customer' in a));assert.equal((await f.repo.events(a.id)).length,1);
 const raw=await f.repo.get(a.id);assert.ok(!raw.customer_cipher.includes('2026-10-10'));assert.equal(protect(secret).decrypt(raw.customer_cipher).rental.return_time,'10:45');
 assert.equal((await f.service.adminGet(a.id)).customer.name,'검증 예약자');await assert.rejects(f.service.get(a.id,hash('other')),{status:404});
 await assert.rejects(f.service.createRental(owner,'rental_request_key_001',{...input,rental:{...schedule,return_time:'11:45'}}),{status:409});
});
test('admin confirms a full-period unit price for every rental line before payment approval',async()=>{
 const f=fixture(),a=await f.service.createRental(owner,'rental_request_key_002',input);await assert.rejects(f.service.approve(a.id,{version:0,stock_confirmed:true}),{status:400});assert.equal((await f.repo.get(a.id)).state,'REQUESTED');
 const approved=await f.service.approve(a.id,{version:0,stock_confirmed:true,rental_prices:[{id:'r1',option:'24시간',unit_price:45000}]});assert.equal(approved.total,90000);assert.equal(approved.shipping,0);assert.equal(approved.rental.start_date,'2026-10-10');
 await assert.rejects(f.service.start(a.id,owner,approved.quote_version),{status:503});
});
test('annual exports retain requested dates and minute times with no fabricated payment totals',async()=>{
 const f=fixture();await f.service.createRental(owner,'rental_request_key_003',input);const output=await f.admin.export({format:'xlsx'}),ExcelJS=require('exceljs'),book=new ExcelJS.Workbook();await book.xlsx.load(output.body);const sheet=book.getWorksheet('주문결제'),headers=sheet.getRow(1).values,values=sheet.getRow(2).values;
 for(const [label,value] of [['주문유형','렌탈'],['대여시작일','2026-10-10'],['대여종료일','2026-10-11'],['수령방문시간','09:15'],['반납방문시간','10:45']])assert.equal(values[headers.indexOf(label)],value);
 assert.equal(sheet.getRow(2).getCell(headers.indexOf('주문총액')).value,null);assert.equal(sheet.getRow(2).getCell(headers.indexOf('실제수령처리일시(KST)')).value,'');
});
test('rental-only activation cannot enable purchases, payments or unauthenticated admin data',async()=>{
 const f=fixture(),h=endpoint({service:f.service,repo:f.repo,adminService:f.admin,sessionKey:secret,password:await passwordHash('rental-test-password'),enabled:false,rentalEnabled:true,clock});
 const session=sessions(secret,clock).issue('rental-cookie','customer',3600);
 async function request(action,method='GET',body,auth=true){const res={headers:{},setHeader(k,v){this.headers[k]=v;},status(code){this.code=code;return this;},json(value){this.value=value;return this;}};await h({url:'/api/orders?action='+action,method,headers:{origin:'https://shop.nadaun.co','x-forwarded-for':'127.0.0.1',...(auth?{cookie:'__Host-nadaun-customer='+session}:{}),'idempotency-key':'rental_http_test_001'},body},res);return res;}
 const config=await request('config');assert.equal(config.value.ordersEnabled,false);assert.equal(config.value.rentalRequestsEnabled,true);
 assert.equal((await request('rental-create','POST',input)).code,201);assert.equal((await request('create','POST',input)).code,503);assert.equal((await request('start','POST',{id:'x'})).code,503);assert.equal((await request('admin-orders')).code,401);
});

 test('rental handover and return keep visit history and reject duplicate or canceled processing',async()=>{
 const f=fixture(),remote={},payment={mode:'live',async get(){return {...remote};}},service=orderService({repo:f.repo,catalog:f.catalog,detail:f.detail,dataKey:secret,payment,clock});
 const request=await service.createRental(owner,'rental_visits_key_004',input),approved=await service.approve(request.id,{version:0,stock_confirmed:true,rental_prices:[{id:'r1',option:'24시간',unit_price:45000}]});
 let row=await f.repo.get(approved.id);row=await f.repo.patch(row,{state:'PAID',payment_mode:'live',payment_provider:'inicis',payment_key:'rental_pg_fixture'},'verification','payment_done');
 Object.assign(remote,{provider:'inicis',orderId:row.id,paymentKey:row.payment_key,totalAmount:row.total,currency:'KRW',status:'DONE'});
 await assert.rejects(service.rentalReturn(row.id,{version:row.version}),{status:409});
 const picked=await service.pickup(row.id,{version:row.version});assert.equal(picked.fulfillment,'processing');assert.equal(picked.rental.actual_pickup_at,clock());assert.equal(picked.rental.pickup_time,'09:15');
 await assert.rejects(service.pickup(row.id,{version:picked.version}),{status:409});
 const returned=await service.rentalReturn(row.id,{version:picked.version});assert.equal(returned.fulfillment,'shipped');assert.equal(returned.rental.actual_return_at,clock());
 assert.deepEqual((await f.repo.events(row.id)).slice(-2).map(e=>e.action),['rental_picked_up','rental_returned']);
 const other=await service.createRental(owner,'rental_visits_key_005',input),q=await service.approve(other.id,{version:0,stock_confirmed:true,rental_prices:[{id:'r1',option:'24시간',unit_price:40000}]});
 let canceled=await f.repo.get(q.id);canceled=await f.repo.patch(canceled,{state:'PAID',payment_mode:'live',payment_provider:'inicis',payment_key:'rental_pg_canceled'},'verification','payment_done');Object.assign(remote,{orderId:canceled.id,paymentKey:canceled.payment_key,totalAmount:canceled.total,status:'CANCELED'});
 await assert.rejects(service.pickup(canceled.id,{version:canceled.version}),{status:409});assert.equal((await f.repo.get(canceled.id)).fulfillment,'unfulfilled');
 });
