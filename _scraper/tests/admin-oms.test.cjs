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
const headers='operation,order_id,version,shipment_id,carrier,tracking,item_id,option,quantity';
const upload=text=>({filename:'tracking.csv',file_base64:Buffer.from(text).toString('base64')});
const invoice=(order,tail=',,검증택배,0123456789,,,')=>upload(headers+'\nship,'+order.id+','+order.version+tail+'\n');
test('purchase workflow preserves financial status and does not infer delivery from dispatch',async()=>{
 const f=fixture();let order=await f.paid(await f.create());assert.equal(order.purchase_workflow.stage,'preparing');
 order=await f.service.workflow(order.id,{version:order.version,stage:'ready'},actor);assert.equal(order.purchase_workflow.stage,'ready');assert.equal(f.calls.length,0);
 assert.equal((await f.admin.list({queue:'purchase-ready'})).summary.orders,1);assert.equal((await f.admin.list({})).workload.purchaseReady,1);
 await assert.rejects(f.service.workflow(order.id,{version:order.version,stage:'delivered'},actor),{status:409});
 order=await f.service.ship(order.id,{version:order.version,carrier:'검증택배',tracking:'0123456789'},actor);assert.equal(order.purchase_workflow.stage,'in_transit');assert.equal(order.shipments[0].delivery_status,'in_transit');
 await assert.rejects(f.service.workflow(order.id,{version:order.version,stage:'preparing'},actor),{status:409});
 order=await f.service.workflow(order.id,{version:order.version,stage:'delivered'},actor);assert.equal(order.state,'PAID');assert.equal(order.fulfillment,'shipped');assert.equal(order.purchase_workflow.stage,'delivered');assert.equal(order.purchase_workflow.delivery_source,'manual');assert.equal((await f.repo.events(order.id)).at(-1).action,'purchase_delivered');
 assert.equal((await f.admin.list({queue:'purchase-transit'})).summary.orders,0);assert.equal((await f.admin.list({queue:'purchase-delivered'})).summary.orders,1);
 const publicOrder=await f.service.get(order.id,owner);assert.ok(!JSON.stringify(publicOrder).includes(actor));assert.ok(!JSON.stringify(publicOrder).includes('_admin_'));assert.equal(publicOrder.shipments[0].delivered_at,f.clock());
 const legacy=await f.paid(await f.create(),'shipped');assert.equal(legacy.purchase_workflow.stage,'in_transit');assert.equal((await f.admin.list({})).workload.purchaseTransit,1);
});
test('workflow bulk applies only eligible CAS versions and rejects duplicates and financial actions',async()=>{
 const f=fixture(),a=await f.paid(await f.create()),b=await f.create(),r=await f.paid(await f.rental()),t=await f.paid(await f.create(),'unfulfilled','test');
 for(const stage of ['PAID','CANCELED','in_transit','refund'])await assert.rejects(f.service.workflowBulk({stage,orders:[{id:a.id,version:a.version}]},actor),{status:400});
 await assert.rejects(f.service.workflowBulk({stage:'ready',orders:[{id:a.id,version:a.version},{id:a.id,version:a.version}]},actor),{status:400});
 const result=await f.service.workflowBulk({stage:'ready',orders:[a,b,r,t].map(o=>({id:o.id,version:o.version}))},actor);assert.equal(result.succeeded,1);assert.equal(result.failed,3);assert.equal(f.calls.length,0);
 assert.equal((await f.service.adminGet(b.id)).state,'REQUESTED');assert.equal((await f.service.adminGet(a.id)).version,a.version+1);
 const again=await f.service.workflowBulk({stage:'delivered',orders:[{id:a.id,version:a.version}]},actor);assert.equal(again.failed,1);assert.equal(again.results[0].status,409);
});
test('customer and all-shipment tracking search filter before pagination and match counts and exports',async()=>{
 const f=fixture();for(let i=0;i<31;i++){const order=await f.create(),row=await f.repo.get(order.id),c=protect(secret).decrypt(row.customer_cipher);c.name=i%2?'홍길동':'다른 고객';c.phone=i%2?'010-1234-5678':'010-9999-8888';await f.repo.patch(row,{customer_cipher:protect(secret).encrypt(c)},actor,'fixture_customer');f.advance(1);}
 const byName=await f.admin.list({search:'홍 길 동',searchField:'customer'});assert.equal(byName.summary.orders,15);assert.equal(byName.orders.length,15);assert.equal(byName.pages,1);
 assert.equal((await f.admin.list({search:'12345678',searchField:'customer'})).summary.orders,15);assert.equal((await f.admin.list({search:'abc1234',searchField:'customer'})).summary.orders,0);assert.equal((await f.admin.list({search:'홍길동',searchField:'order'})).summary.orders,0);
 assert.equal((await f.admin.list({search:'NS-',searchField:'all'})).summary.orders,31);assert.equal((await f.admin.list({search:'NS-',page:2})).orders.length,6);
 let shipped=await f.paid(await f.create());shipped=await f.service.ship(shipped.id,{version:shipped.version,carrier:'검증택배',tracking:'0987654321'},actor);
 assert.deepEqual((await f.admin.list({search:'987654',searchField:'tracking'})).orders.map(o=>o.id),[shipped.id]);
 assert.equal((await f.admin.export({search:'홍길동',searchField:'customer',format:'csv'})).body.toString().trim().split('\r\n').length,16);
});
test('selected exports strictly validate IDs and enforce current filters without silently omitting rows',async()=>{
 const f=fixture(),a=await f.create(),b=await f.create();
 const selected=await f.admin.export({ids:[a.id],format:'csv'});assert.ok(selected.body.toString().includes(a.id));assert.ok(!selected.body.toString().includes(b.id));
 for(const ids of [[],[a.id,a.id],['bad'],Array(51).fill(a.id),'all'])await assert.rejects(f.admin.export({ids,format:'csv'}),{status:400});
 await assert.rejects(f.admin.export({ids:[a.id,'NS-missing'],format:'csv'}),{status:409});await assert.rejects(f.admin.export({ids:[a.id],state:'PAID',format:'csv'}),{status:409});
});
test('invoice preview never ships; explicit apply ships and same file is idempotent across fresh previews',async()=>{
 const f=fixture(),order=await f.paid(await f.create()),file=invoice(order),preview=await f.admin.invoicePreview(file,actor);
 assert.equal(preview.valid,true);assert.equal(preview.operations[0].items[0].quantity,1);assert.equal(preview.totals.rows,1);assert.equal(f.calls.length,0);assert.equal((await f.repo.get(order.id)).version,order.version);
 const result=await f.admin.invoiceApply({preview_token:preview.preview_token,index:0},actor);assert.equal(result.ok,true);assert.equal(result.duplicate,false);assert.equal(result.order.shipments.length,1);assert.equal(result.order.shipments[0].tracking,'0123456789');assert.equal(f.calls.length,1);
 const repeat=await f.admin.invoiceApply({preview_token:preview.preview_token,index:0},actor);assert.equal(repeat.duplicate,true);assert.equal(repeat.order.version,result.order.version);assert.equal(f.calls.length,1);
 const fresh=await f.admin.invoicePreview(file,actor);assert.equal(fresh.valid,true);assert.equal(fresh.operations[0].duplicate,true);assert.equal((await f.admin.invoiceApply({preview_token:fresh.preview_token,index:0},actor)).duplicate,true);
 const raw=await f.repo.get(order.id);assert.ok(!raw.customer_cipher.includes('0123456789'));assert.ok(!JSON.stringify(await f.service.get(order.id,owner)).includes('_admin_imports'));assert.equal((await f.repo.events(order.id)).filter(e=>e.action==='order_shipped').length,1);
});
test('invoice preview rejects malformed rows, duplicate quantities, changed versions and unauthorized token reuse',async()=>{
 const f=fixture(),order=await f.paid(await f.create()),file=invoice(order);
 const bad=await f.admin.invoicePreview(upload(headers+'\nship,'+order.id+','+order.version+',,검증택배,0123456789,purchase,,2'),actor);assert.equal(bad.valid,false);assert.equal(bad.errors.length,1);assert.ok(!bad.preview_token);
 const duplicate=await f.admin.invoicePreview(upload(headers+'\nship,'+order.id+','+order.version+',,검증택배,0123456789,purchase,,1\nship,'+order.id+','+order.version+',,검증택배,0123456789,purchase,,1'),actor);assert.equal(duplicate.valid,false);
 const preview=await f.admin.invoicePreview(file,actor);await assert.rejects(f.admin.invoiceApply({preview_token:preview.preview_token+'x',index:0},actor),{status:403});await assert.rejects(f.admin.invoiceApply({preview_token:preview.preview_token,index:0},'other@example.invalid'),{status:409});
 await f.service.saveNote(order.id,{version:order.version,note:'다른 관리자 변경'},actor);await assert.rejects(f.admin.invoiceApply({preview_token:preview.preview_token,index:0},actor),{status:409});assert.equal(f.calls.length,0);
 f.advance(1800001);await assert.rejects(f.admin.invoiceApply({preview_token:preview.preview_token,index:0},actor),{status:409});
});
test('invoice update requires a shipment ID and preserves quantities and delivery records',async()=>{
 const f=fixture();let order=await f.paid(await f.create());order=await f.service.ship(order.id,{version:order.version,carrier:'검증택배',tracking:'123456789'},actor);order=await f.service.workflow(order.id,{version:order.version,stage:'delivered'},actor);
 const preview=await f.admin.invoicePreview(upload(headers+'\nupdate,'+order.id+','+order.version+','+order.shipments[0].id+',수정택배,0011223344,,,'),actor);assert.equal(preview.valid,true);
 const changed=await f.admin.invoiceApply({preview_token:preview.preview_token,index:0},actor);assert.equal(changed.order.shipments.length,1);assert.equal(changed.order.purchase_workflow.stage,'delivered');assert.equal(changed.order.shipments[0].tracking,'0011223344');assert.equal(f.calls.length,1);
});
test('CSV and XLSX enforce format, formulas, leading-zero tracking, compressed size and row limits',async()=>{
 const f=fixture(),order=await f.paid(await f.create()),ExcelJS=require('exceljs');
 const book=new ExcelJS.Workbook(),sheet=book.addWorksheet('송장');sheet.addRow(headers.split(','));sheet.addRow(['ship',order.id,order.version,'','검증택배','0001234567','','','']);
 let file={filename:'orders.xlsx',file_base64:Buffer.from(await book.xlsx.writeBuffer()).toString('base64')};assert.equal((await f.admin.invoicePreview(file,actor)).valid,true);
 sheet.getCell('F2').value=1234567;file.file_base64=Buffer.from(await book.xlsx.writeBuffer()).toString('base64');await assert.rejects(f.admin.invoicePreview(file,actor),{status:400});
 sheet.getCell('F2').value={formula:'1234567',result:1234567};file.file_base64=Buffer.from(await book.xlsx.writeBuffer()).toString('base64');await assert.rejects(f.admin.invoicePreview(file,actor),{status:400});
 for(const file of [upload('"unterminated'),upload(headers+'\n'+Array(501).fill('ship,x,0,,abc,123456,,,').join('\n')),upload('x'.repeat(1048577)),{filename:'x.csv',file_base64:Buffer.from([0xff,0xfe,0x00]).toString('base64')},{filename:'x.xlsx',file_base64:Buffer.from('not a zip').toString('base64')}])await assert.rejects(f.admin.invoicePreview(file,actor));
});
test('new endpoints keep origin/session gates, do not trust actor and allow selected POST export',async()=>{
 const f=fixture(),order=await f.paid(await f.create()),handler=endpoint({service:f.service,repo:f.repo,adminService:f.admin,password:'unused',email:actor,sessionKey:secret,enabled:false,clock:f.clock}),cookie='__Host-nadaun-admin='+sessions(secret,f.clock).issue(actor,'admin',3600);
 for(const action of ['admin-workflow','admin-workflow-bulk','admin-invoice-preview','admin-invoice-apply','admin-export'])assert.equal((await request(handler,action,'POST',{})).code,401);
 const body={stage:'ready',orders:[{id:order.id,version:order.version}],actor:'forged'};assert.equal((await request(handler,'admin-workflow-bulk','POST',body,{cookie,origin:'https://evil.invalid'})).code,403);
 const changed=await request(handler,'admin-workflow-bulk','POST',body,{cookie});assert.equal(changed.code,200);assert.equal(changed.body.succeeded,1);assert.equal((await f.repo.events(order.id)).at(-1).actor,actor);
 const exported=await request(handler,'admin-export','POST',{filters:{},ids:[order.id],format:'csv'},{cookie});assert.equal(exported.code,200);assert.equal(exported.headers['Cache-Control'],'no-store');
 const preview=await request(handler,'admin-invoice-preview','POST',invoice(changed.body.results[0].order),{cookie});assert.equal(preview.code,200);assert.equal(preview.body.valid,true);assert.equal(f.calls.length,0);
});
test('simultaneous invoice applies have one CAS winner and audit failure rolls back the complete import ledger',async()=>{
 const f=fixture(),order=await f.paid(await f.create()),preview=await f.admin.invoicePreview(invoice(order),actor),input={preview_token:preview.preview_token,index:0};
 const raced=await Promise.allSettled([f.admin.invoiceApply(input,actor),f.admin.invoiceApply(input,actor)]);assert.equal(raced.filter(x=>x.status==='fulfilled'&&!x.value.duplicate).length,1);assert.equal((await f.service.adminGet(order.id)).shipments.length,1);
 assert.equal((await f.repo.events(order.id)).filter(e=>e.action==='order_shipped').length,1);assert.equal((await f.admin.invoiceApply(input,actor)).duplicate,true);
 const g=fixture(),fresh=await g.paid(await g.create()),plan=await g.admin.invoicePreview(invoice(fresh),actor),before=await g.repo.get(fresh.id);
 g.sql.exec("CREATE TRIGGER fail_import BEFORE INSERT ON shop_order_events WHEN NEW.action='order_shipped' BEGIN SELECT RAISE(ABORT,'fixture audit failure'); END;");
 await assert.rejects(g.admin.invoiceApply({preview_token:plan.preview_token,index:0},actor));const after=await g.repo.get(fresh.id);assert.equal(after.version,before.version);assert.equal(after.customer_cipher,before.customer_cipher);assert.equal(after.fulfillment,'unfulfilled');
});
test('encrypted search fails closed above 10000 candidates and ordinary unsearched counts stay available',async()=>{
 const f=fixture(),original=await f.create(),row=await f.repo.get(original.id),keys=Object.keys(row),insert=f.sql.prepare(`INSERT INTO shop_orders(${keys.join(',')}) VALUES(${keys.map(()=>'?').join(',')})`);
 f.sql.exec('BEGIN');for(let i=1;i<=10000;i++){const copy={...row,id:'NS-scan_'+i,request_key:'scan_'+i,confirm_key:'scan_confirm_'+i};insert.run(...keys.map(key=>copy[key]));}f.sql.exec('COMMIT');
 await assert.rejects(f.admin.list({search:'테스트',searchField:'customer'}),{status:413});await assert.rejects(f.admin.export({search:'010',searchField:'all',format:'csv'}),{status:413});
 assert.equal((await f.admin.list({})).summary.orders,10001);assert.equal((await f.admin.list({search:original.id,searchField:'order'})).summary.orders,1);
 assert.equal((await f.admin.export({ids:[original.id],search:'테스트',searchField:'customer',format:'csv'})).body.toString().trim().split('\r\n').length,2);
});
test('multi-line partial imports preserve quantities, follow-up shipment tracking search and case queues',async()=>{
 const f=fixture();let order=await f.service.create(owner,'oms_three_units_request',{customer,items:[{id:'purchase',option:'',quantity:3}]});order=await f.paid(order);
 const preview=await f.admin.invoicePreview(upload(headers+'\nship,'+order.id+','+order.version+',,검증택배,111111111,purchase,,1'),actor);assert.equal(preview.valid,true);
 order=(await f.admin.invoiceApply({preview_token:preview.preview_token,index:0},actor)).order;assert.equal(order.purchase_workflow.partial,true);assert.equal(order.purchase_workflow.stage,'in_transit');await assert.rejects(f.service.workflow(order.id,{version:order.version,stage:'delivered'},actor),{status:409});
 const first=order.shipments[0].id;order=await f.service.ship(order.id,{version:order.version,carrier:'두번째택배',tracking:'222222222'},actor);
 assert.equal((await f.admin.list({search:'111111111',searchField:'tracking'})).summary.orders,1);assert.equal((await f.admin.list({search:'222222222',searchField:'tracking'})).summary.orders,1);
 order=await f.service.createCase(order.id,{version:order.version,kind:'return',shipment_id:first,items:[{id:'purchase',option:'',quantity:1}],reason:'검증 반품'},actor);
 assert.equal((await f.admin.list({queue:'purchase-cases'})).summary.orders,1);assert.equal((await f.admin.list({search:'테스트',searchField:'customer'})).workload.purchaseCases,1);
});
test('decompression bombs are rejected before parsing XLSX XML',async()=>{
 const f=fixture(),ExcelJS=require('exceljs'),book=new ExcelJS.Workbook(),sheet=book.addWorksheet('large');sheet.addRow(headers.split(','));
 // Highly compressible strings produce a small ZIP with oversized expanded XML.
 for(let i=0;i<300;i++)sheet.addRow(['ship','X'.repeat(30000)+i,0,'','검증택배','123456789','','','']);
 const bytes=Buffer.from(await book.xlsx.writeBuffer());assert.ok(bytes.length<1048576);
 await assert.rejects(f.admin.invoicePreview({filename:'oversize.xlsx',file_base64:bytes.toString('base64')},actor),{status:400});
});
test('private search uses POST without URL terms and keeps no-store authentication',async()=>{
 const f=fixture();await f.create();const handler=endpoint({service:f.service,repo:f.repo,adminService:f.admin,password:'unused',email:actor,sessionKey:secret,enabled:false,clock:f.clock}),cookie='__Host-nadaun-admin='+sessions(secret,f.clock).issue(actor,'admin',3600);
 const result=await request(handler,'admin-orders','POST',{filters:{search:'테스트 고객',searchField:'customer'}},{cookie});assert.equal(result.code,200);assert.equal(result.body.summary.orders,1);assert.equal(result.headers['Cache-Control'],'no-store');
});
test('draft routes require owner session, retain actor and Origin gates and remain optional',async()=>{
 const f=fixture(),calls=[],draftService={async products(input,who){calls.push(['products',who,input]);return {products:[],total:0};},async list(input,who){calls.push(['list',who,input]);return {drafts:[],total:0,page:1,pageSize:25,pages:1};},async get(id,who){calls.push(['get',who,id]);return {id};},async create(input,who){calls.push(['create',who,input]);return {id:'ND-fixture'};},async update(id,input,who){calls.push(['update',who,input]);return {id};},async review(id,input,who){calls.push(['review',who,input]);return {id};},async void(id,input,who){calls.push(['void',who,input]);return {id};},async quote(id,who){calls.push(['quote',who,id]);return {filename:'draft-quote.html',type:'text/html; charset=utf-8',body:'<!doctype html><title>초안</title>'};}};
 const options={service:f.service,repo:f.repo,adminService:f.admin,password:'unused',email:actor,sessionKey:secret,enabled:false,clock:f.clock},handler=endpoint({...options,draftService}),cookie='__Host-nadaun-admin='+sessions(secret,f.clock).issue(actor,'admin',3600);
 assert.equal((await request(handler,'config')).body.adminDraftsEnabled,true);assert.equal((await request(endpoint(options),'config')).body.adminDraftsEnabled,false);
 for(const action of ['admin-drafts','admin-draft-products&kind=purchase','admin-draft&id=ND-fixture','admin-draft-quote&id=ND-fixture'])assert.equal((await request(handler,action)).code,401);
 for(const action of ['admin-draft-create','admin-draft-update','admin-draft-review','admin-draft-void']){assert.equal((await request(handler,action,'POST',{id:'ND-fixture'})).code,401);assert.equal((await request(handler,action,'POST',{id:'ND-fixture'},{cookie,origin:'https://evil.invalid'})).code,403);const result=await request(handler,action,'POST',{id:'ND-fixture',actor:'forged'},{cookie});assert.equal(result.code,action==='admin-draft-create'?201:200);assert.ok(result.body.draft);}
 assert.equal((await request(handler,'admin-draft-products&kind=purchase','GET',null,{cookie})).body.total,0);
 const list=await request(handler,'admin-drafts','POST',{filters:{search:'가상 고객'}},{cookie});assert.equal(list.code,200);assert.equal(list.body.total,0);
 const allExport=await request(handler,'admin-export','POST',{filters:{search:'테스트',searchField:'customer'},format:'csv'},{cookie});assert.equal(allExport.code,200);
 const get=await request(handler,'admin-draft&id=ND-fixture','GET',null,{cookie});assert.equal(get.body.draft.id,'ND-fixture');
 const quote=await request(handler,'admin-draft-quote&id=ND-fixture','GET',null,{cookie});assert.equal(quote.code,200);assert.match(quote.headers['Content-Security-Policy'],/default-src 'none'/);assert.equal(quote.headers['Cache-Control'],'no-store');assert.ok(calls.every(call=>call[1]===actor));
 assert.equal((await request(endpoint(options),'admin-drafts','GET',null,{cookie})).code,404);assert.equal(f.calls.length,0);
});
