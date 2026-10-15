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
function fixture(labelProvider=null){
 let now=Date.parse('2026-10-15T03:00:00Z');const clock=()=>now;
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync('server/commerce/schema.sql','utf8'));
 const db={async batch(statements){sql.exec('BEGIN');try{const out=statements.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return out;}catch(error){sql.exec('ROLLBACK');throw error;}},async query(s,p=[]){return (await this.batch([{sql:s,params:p}]))[0];}};
 const catalog={meta:{synced_at:new Date(now).toISOString(),revision:'workflow-fixture'},redirects:{},products:[{id:'purchase',kind:'purchase',name:'검증 구매',status:'sale',price:10000,shipping_class:'standard',offers:[{source:'smartstore'}]},{id:'rental',kind:'rental',name:'검증 렌탈',status:'sale'}]};
 const detail=()=>({rental:{rates:[{label:'24시간',price:10000}]}}),calls=[];
 const payment={mode:'live',prepare(row){calls.push('prepare');return {id:row.id};},async get(key){calls.push('get');const row=(await db.query('SELECT * FROM shop_orders WHERE payment_key=?',[key]))[0];return {provider:'inicis',orderId:row.id,paymentKey:key,totalAmount:row.total,currency:'KRW',status:'DONE'};}};
 const repo=repository(db,clock),service=orderService({repo,catalog,detail,dataKey:secret,sessionKey:secret,payment,labelProvider,clock}),admin=adminService({db,service,dataKey:secret,clock});
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
const {goodsflow}=require('../../server/commerce/goodsflow.cjs');
function providerFixture(){
 const calls=[],rows=new Map();let timeout=false;
 const c={contractId:'1000000001',status:'APPROVED',transporter:'LOGEN',startDate:'2026-01-01',endDate:'2026-12-31',deliveryCalcStandard:'CREDIT_CALC',center:{code:'1000000002',name:'가상 출고지',phoneNo1:'01000000000',zipCode:'01234',address1:'테스트 주소',address2:'',enabled:true},contractRates:[{boxSize:'B05',boxSizeName:'소형',creditCost:3000}]};
 const fetcher=async(url,options)=>{
  calls.push({url,options});const path=new URL(url).pathname;let data;
  if(path==='/api/contracts')data=[c];
  else if(options.method==='POST'){
   const body=JSON.parse(options.body),item=body.items[0];
   rows.set(item.uniqueId,{uniqueId:item.uniqueId,id:String(100000+rows.size),transporter:item.transporter,centerCode:item.centerCode,status:'REQUEST',invoiceNo:null});
   if(timeout)throw Error('synthetic response lost');
   data={totalCnt:1,successCnt:1,items:[{success:true,data:{uniqueId:item.uniqueId,serviceId:rows.get(item.uniqueId).id}}]};
  }else if(options.method==='PUT')data={uri:'https://admin.goodsflow.io/invoice-print/public/print/synthetic-token',requestCount:JSON.parse(options.body).length,printCount:JSON.parse(options.body).length};
  else data=[...rows.values()].filter(r=>path.endsWith(r.uniqueId));
  return {ok:true,json:async()=>({success:true,data})};
 };
 const p=goodsflow({SHOP_GOODSFLOW_MODE:'live',SHOP_GOODSFLOW_ENABLED:'true',SHOP_GOODSFLOW_API_KEY:'synthetic-key'},fetcher,()=>Date.parse('2026-10-15T03:00:00Z'));
 return {p,c,calls,rows,setTimeout:v=>timeout=v};
}
async function ready(f){let o=await f.paid(await f.create());return f.service.workflow(o.id,{version:o.version,stage:'ready'},actor);}
const registration=o=>({id:o.id,version:o.version,contract_id:'1000000001',box:'B05',confirmed:true});
test('automatic labels stay off without explicit live credentials; every route requires admin',async()=>{
 const f=fixture();assert.equal((await f.service.labelStatus()).enabled,false);await assert.rejects(f.service.labelRegister({}),{status:503});assert.deepEqual(await f.service.labelDrain(),{state:'disabled',processed:0});
 const handler=endpoint({service:f.service,repo:f.repo,sessionKey:secret,password:await passwordHash('fixture-password-0123456789')});
 for(const [action,method] of [['admin-label-status','GET'],['admin-label-preview','POST'],['admin-label-register','POST'],['admin-label-print','POST'],['admin-label-sync','POST']])assert.equal((await request(handler,action,method,method==='POST'?{}:undefined)).code,401);
 assert.equal(goodsflow({SHOP_GOODSFLOW_ENABLED:'true',SHOP_GOODSFLOW_API_KEY:'key'}).enabled,false);
});
test('preview is read-only; booking reserves once and printing is not shipping',async()=>{
 const pf=providerFixture(),f=fixture(pf.p),o=await ready(f),body=registration(o);
 const preview=await f.service.labelPreview({...body,orders:[{id:o.id,version:o.version}]});assert.equal(preview.results[0].ok,true);assert.equal((await f.repo.get(o.id)).version,o.version);
 assert.equal(pf.calls.filter(c=>c.options.method==='POST').length,0);
 const result=await f.service.labelRegister(body,actor);assert.equal(result.order.admin_shipping_label.status,'registered');assert.equal(result.order.fulfillment,'unfulfilled');
 await assert.rejects(f.service.labelRegister({...body,version:result.order.version},actor),{status:409});assert.equal(pf.calls.filter(c=>c.options.method==='POST').length,1);
 assert.equal((await f.db.query('SELECT * FROM shop_shipping_sync')).length,1);
 await assert.rejects(f.service.ship(o.id,{version:result.order.version,carrier:'로젠택배',tracking:'0123456789'},actor),{status:409});
 const link=await f.service.labelPrint({ids:[o.id],include_printed:false});assert.match(link.uri,/^https:\/\/admin.goodsflow.io\//);
 const remote=[...pf.rows.values()][0];remote.status='PRINTED';remote.invoiceNo='0123456789';
 const printed=(await f.service.labelSync(o.id)).order;assert.equal(printed.tracking,'0123456789');assert.equal(printed.fulfillment,'unfulfilled');assert.equal(printed.shipments.length,0);assert.equal(printed.purchase_workflow.stage,'ready');
 await assert.rejects(f.service.labelPrint({ids:[o.id],include_printed:false}),{status:409});await f.service.labelPrint({ids:[o.id],include_printed:true});
 const publicOrder=await f.service.get(o.id,owner);assert.ok(!JSON.stringify(publicOrder).includes('admin_shipping_label'));assert.ok(!JSON.stringify(publicOrder).includes('unique_id'));assert.ok(!(await f.repo.get(o.id)).customer_cipher.includes('0123456789'));
});
test('pickup and delivered are reconciled once, older events cannot undo delivery',async()=>{
 const pf=providerFixture(),f=fixture(pf.p),o=await ready(f);await f.service.labelRegister(registration(o),actor);const remote=[...pf.rows.values()][0];remote.status='PICKUP';remote.invoiceNo='0123456789';
 let result=(await f.service.labelSync(o.id)).order;assert.equal(result.shipments.length,1);assert.equal(result.purchase_workflow.stage,'in_transit');
 remote.status='COMPLETED';result=(await f.service.labelSync(o.id)).order;assert.equal(result.shipments.length,1);assert.equal(result.purchase_workflow.stage,'delivered');assert.equal(result.purchase_workflow.delivery_source,'goodsflow');assert.equal(result.shipments[0].delivery_source,'goodsflow');assert.equal((await f.db.query('SELECT * FROM shop_shipping_sync'))[0].next_attempt,null);
 const listing=await f.admin.list({queue:'purchase-delivered'});assert.equal(listing.summary.purchaseDelivered,1);assert.equal(listing.orders[0].id,o.id);assert.equal((await f.admin.list({queue:'purchase-transit'})).orders.length,0);
 const searched=await f.admin.list({queue:'purchase-delivered',search:'테스트 고객',searchField:'customer'});assert.equal(searched.summary.purchaseDelivered,1);assert.equal(searched.orders.length,1);
 remote.status='PRINTED';result=(await f.service.labelSync(o.id)).order;assert.equal(result.admin_shipping_label.status,'delivered');assert.equal(result.shipments.length,1);
});
test('lost POST response recovers by unique ID without a second booking, including cron',async()=>{
 const pf=providerFixture(),f=fixture(pf.p),o=await ready(f);pf.setTimeout(true);
 await assert.rejects(f.service.labelRegister(registration(o),actor),{status:503});let current=await f.service.adminGet(o.id);assert.equal(current.admin_shipping_label.status,'pending');
 await assert.rejects(f.service.labelRegister({...registration(current)},actor),{status:409});
 f.advance(61000);const drained=await f.service.labelDrain();assert.equal(drained.processed,1);assert.equal(drained.results[0].ok,true);current=await f.service.adminGet(o.id);assert.equal(current.admin_shipping_label.status,'registered');assert.equal(pf.calls.filter(c=>c.options.method==='POST').length,1);
});
test('concurrent registration reserves once; stale versions and wrong addresses fail before POST',async()=>{
 const pf=providerFixture(),f=fixture(pf.p),o=await ready(f);const results=await Promise.allSettled([f.service.labelRegister(registration(o),actor),f.service.labelRegister(registration(o),actor)]);assert.equal(results.filter(r=>r.status==='fulfilled').length,1);assert.equal(pf.calls.filter(c=>c.options.method==='POST').length,1);
 let other=await ready(f),row=await f.repo.get(other.id),customer=protect(secret).decrypt(row.customer_cipher);customer.address='가'.repeat(101);await f.repo.patch(row,{customer_cipher:protect(secret).encrypt(customer)},actor,'fixture_long_address');other=await f.service.adminGet(other.id);await assert.rejects(f.service.labelRegister(registration(other),actor),{status:400});assert.equal(pf.calls.filter(c=>c.options.method==='POST').length,1);
});
test('only paid ready purchase orders and approved valid contracts can be booked',async()=>{
 const pf=providerFixture(),f=fixture(pf.p),unpaid=await f.create(),preparing=await f.paid(await f.create()),rental=await f.paid(await f.rental()),test=await f.paid(await f.create(),'unfulfilled','test');
 for(const o of [unpaid,preparing,rental,test])await assert.rejects(f.service.labelRegister(registration(o),actor),{status:409});
 const o=await ready(f);pf.c.endDate='2026-01-01';await assert.rejects(f.service.labelRegister(registration(o),actor),{status:409});assert.equal(pf.calls.filter(c=>c.options.method==='POST').length,0);
});
test('mismatched carrier result and canceled payment cannot mark an order shipped',async()=>{
 const pf=providerFixture(),f=fixture(pf.p),o=await ready(f);await f.service.labelRegister(registration(o),actor);const remote=[...pf.rows.values()][0];remote.status='COMPLETED';remote.invoiceNo='0123456789';remote.centerCode='wrong';await assert.rejects(f.service.labelSync(o.id),{status:409});remote.centerCode='1000000002';
 await f.repo.patch(await f.repo.get(o.id),{state:'CANCELED'},actor,'fixture_cancel');const current=(await f.service.labelSync(o.id)).order;assert.equal(current.state,'CANCELED');assert.equal(current.fulfillment,'unfulfilled');assert.equal(current.admin_shipping_label.status,'review');
});
test('provider sends raw Authorization key to official host only and rejects unsafe/partial print URLs',async()=>{
 const pf=providerFixture();await pf.p.contracts();assert.equal(pf.calls[0].options.headers.Authorization,'synthetic-key');assert.equal(pf.calls[0].options.redirect,'error');
 for(const uri of ['https://evil.invalid/print','https://admin.goodsflow.io.evil.invalid/invoice-print/public/print/x','javascript:alert(1)']){
  const p=goodsflow({SHOP_GOODSFLOW_MODE:'live',SHOP_GOODSFLOW_API_KEY:'synthetic-key'},async()=>({ok:true,json:async()=>({success:true,data:{uri,requestCount:1,printCount:1}})}));await assert.rejects(p.print(['1']),{status:503});
 }
});
