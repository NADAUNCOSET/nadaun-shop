const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {DatabaseSync}=require('node:sqlite');
const {repository,orderService}=require('../../server/commerce/orders.cjs');
const {protect,hash,sessions}=require('../../server/commerce/security.cjs');
const {endpoint}=require('../../server/commerce/http.cjs');
const secret='ef'.repeat(32),owner=hash('fulfillment-customer'),actor='staff@example.invalid',clock=()=>Date.parse('2026-10-15T04:00:00Z');
const shipping={carrier:'검증택배',tracking:'123456789012'},line=(option,quantity)=>({id:'p1',option,quantity});
async function fixture(){
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync('server/commerce/schema.sql','utf8'));
 const db={async batch(statements){sql.exec('BEGIN');try{const result=statements.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return result;}catch(e){sql.exec('ROLLBACK');throw e;}},async query(sql,params=[]){return (await this.batch([{sql,params}]))[0];}};
 const catalog={meta:{synced_at:new Date(clock()).toISOString(),revision:'fulfillment-test'},redirects:{},products:[{id:'p1',kind:'purchase',name:'검증 장비',status:'sale',price:10000,shipping_class:'standard',offers:[{source:'smartstore'}]}]},detail=()=>({options:[{name:'A',additional_price:0},{name:'B',additional_price:0}]}),repo=repository(db,clock),calls=[],remote={status:'DONE'};
 const payment={mode:'live',async get(key){calls.push('get');const row=(await db.query('SELECT * FROM shop_orders WHERE payment_key=?',[key]))[0];return {provider:'toss',orderId:row.id,paymentKey:key,totalAmount:row.total,currency:'KRW',...remote};}};
 const service=orderService({repo,catalog,detail,dataKey:secret,payment,clock});
 const input={customer:{name:'테스트 주문자',phone:'010-0000-0000',postcode:'01234',address:'테스트 주소',address_detail:'검증용',consent:true},items:[line('A',3),line('B',2)]};
 const order=await service.create(owner,'fulfillment_request_001',input);await repo.patch(await repo.get(order.id),{state:'PAID',payment_mode:'live',payment_provider:'toss',payment_key:'fulfillment_payment_001'},'fixture','payment_done');
 const current=()=>service.adminGet(order.id),ship=async items=>{const currentOrder=await current();return service.ship(order.id,{version:currentOrder.version,...shipping,...(items?{items}:{})},actor);};
 const createCase=async(kind='return',items=[line('A',1)],shipmentId)=>{const currentOrder=await current();return service.createCase(order.id,{version:currentOrder.version,kind,shipment_id:shipmentId||currentOrder.shipments[0].id,items,reason:'검수 결과 처리 요청'},actor);};
 const advanceCase=async(status,note='처리 내역 확인',extra={})=>{const currentOrder=await current();return service.updateCase(order.id,{version:currentOrder.version,case_id:currentOrder.admin_cases[0].id,status,note,...extra},actor);};
 return {sql,db,catalog,repo,service,payment,calls,remote,order,input,current,ship,createCase,advanceCase};
}
test('partial shipments account per option, finish only at full quantity, and expose no admin metadata',async()=>{
 const f=await fixture(),first=await f.ship([line('A',1)]);assert.equal(first.fulfillment,'processing');assert.equal(first.shipments.length,1);assert.equal(first.shipments[0].items[0].quantity,1);
 const second=await f.ship([line('B',2)]);assert.equal(second.fulfillment,'processing');const full=await f.ship();assert.equal(full.fulfillment,'shipped');assert.deepEqual(full.shipments[2].items.map(x=>[x.option,x.quantity]),[['A',2]]);
 await assert.rejects(f.ship(),{status:409});assert.equal((await f.current()).shipments.length,3);
 const publicOrder=await f.service.get(f.order.id,owner);assert.equal(publicOrder.shipments.length,3);assert.ok(!JSON.stringify(publicOrder).includes(actor));assert.ok(!('admin_cases' in publicOrder));assert.ok(!JSON.stringify(full.customer).includes('_admin_'));
 const raw=await f.repo.get(f.order.id),stored=protect(secret).decrypt(raw.customer_cipher);assert.equal(stored._admin_shipments[0].actor,actor);assert.ok(!raw.customer_cipher.includes(shipping.tracking));
 assert.deepEqual((await f.repo.events(f.order.id)).slice(-3).map(e=>e.action),['order_partially_shipped','order_partially_shipped','order_shipped']);
});
test('wrong variants, fractional, duplicate and excessive shipment quantities fail before the provider query',async()=>{
 for(const items of [[line('A',4)],[line('missing',1)],[line('A',1.1)],[line('A',0)],[line('A',1),line('A',1)],[]]){const f=await fixture();await assert.rejects(f.service.ship(f.order.id,{version:1,...shipping,items},actor));assert.equal(f.calls.length,0);assert.equal((await f.current()).shipments.length,0);}
});
test('concurrent partial shipments cannot duplicate allocation or audit rows',async()=>{
 const f=await fixture(),input={version:1,...shipping,items:[line('A',2)]},result=await Promise.allSettled([f.service.ship(f.order.id,input,actor),f.service.ship(f.order.id,input,actor)]);assert.equal(result.filter(r=>r.status==='fulfilled').length,1);assert.equal((await f.current()).shipments.length,1);assert.equal((await f.repo.events(f.order.id)).length,3);
});
test('shipment correction changes only tracking on the selected shipment and preserves prior values privately',async()=>{
 const f=await fixture();await f.ship([line('A',1)]);const order=await f.ship([line('B',1)]),id=order.shipments[0].id;
 const updated=await f.service.updateShipment(order.id,{version:order.version,shipment_id:id,carrier:'다른택배',tracking:'9876543210'},actor);assert.equal(updated.shipments[0].tracking,'9876543210');assert.equal(updated.shipments[1].tracking,shipping.tracking);assert.equal(updated.tracking,shipping.tracking);assert.deepEqual(updated.shipments[0].items,order.shipments[0].items);assert.equal(updated.fulfillment,'processing');
 const stored=protect(secret).decrypt((await f.repo.get(order.id)).customer_cipher);assert.equal(stored._admin_shipments[0].corrections[0].tracking,shipping.tracking);assert.ok(!JSON.stringify((await f.service.get(order.id,owner)).shipments).includes('corrections'));
 await assert.rejects(f.service.updateShipment(order.id,{version:updated.version,shipment_id:id,...shipping,items:[line('A',3)]},actor),{status:400});assert.equal((await f.repo.events(order.id)).at(-1).action,'order_tracking_updated');
});
test('legacy completed orders retain repeated tracking edits without inventing new shipments',async()=>{
 const f=await fixture();await f.repo.patch(await f.repo.get(f.order.id),{fulfillment:'shipped',...shipping},'fixture','order_shipped');
 for(const tracking of ['2222222222','3333333333']){const order=await f.current(),updated=await f.service.ship(order.id,{version:order.version,carrier:'기존택배',tracking},actor);assert.equal(updated.shipments.length,1);assert.equal(updated.shipments[0].id,'legacy');assert.equal(updated.shipments[0].created_at,null);assert.equal(updated.tracking,tracking);}
 assert.equal(f.calls.length,0);await assert.rejects(f.ship([line('A',1)]),{status:409});
});
test('canceled payment blocks new shipment without recording a false shipment',async()=>{
 const f=await fixture();f.remote.status='CANCELED';await assert.rejects(f.ship([line('A',1)]),{status:409});assert.equal((await f.current()).state,'CANCELED');assert.equal((await f.current()).shipments.length,0);
});
test('cases bind to a shipment and prevent duplicate, excess or wrong-shipment returns',async()=>{
 const f=await fixture();await f.ship([line('A',2)]);const order=await f.ship([line('A',1)]),first=order.shipments[0].id,second=order.shipments[1].id;
 await f.createCase('return',[line('A',1)],first);await f.createCase('exchange',[line('A',1)],first);await assert.rejects(f.createCase('return',[line('A',1)],first),{status:409});await assert.rejects(f.createCase('return',[line('B',1)],first),{status:409});
 const current=await f.createCase('return',[line('A',1)],second);assert.equal(current.admin_cases.length,3);assert.equal(current.state,'PAID');assert.equal(current.fulfillment,'processing');
});
test('case transitions never imply a refund; rejected allocation is released but returned quantity stays consumed',async()=>{
 const f=await fixture();await f.ship([line('A',1)]);await f.createCase();const calls=f.calls.length;await assert.rejects(f.advanceCase('closed'),{status:409});await f.advanceCase('approved');await f.advanceCase('returning','회수 접수',{carrier:'회수택배',tracking:'5555555555'});await f.advanceCase('received');const closed=await f.advanceCase('closed','물품 회수 기록 종결, 환불 별도 확인');assert.equal(closed.state,'PAID');assert.equal(closed.admin_cases[0].return_tracking,'5555555555');assert.equal(f.calls.length,calls);await assert.rejects(f.createCase(),{status:409});
 const g=await fixture();await g.ship([line('A',1)]);await g.createCase();await g.advanceCase('rejected','고객 요청 철회');assert.equal((await g.createCase()).admin_cases.length,2);
 const publicOrder=await f.service.get(f.order.id,owner);assert.ok(!JSON.stringify(publicOrder).includes('별도 확인'));assert.ok(!JSON.stringify(publicOrder).includes(actor));
});
test('exchange reshipment consumes only the case allocation and enables returns against replacement delivery',async()=>{
 const f=await fixture();await f.ship([line('A',2)]);await f.createCase('exchange',[line('A',2)]);await f.advanceCase('approved');await f.advanceCase('received');let order=await f.current(),caseId=order.admin_cases[0].id;
 await assert.rejects(f.advanceCase('closed'),{status:409});
 order=await f.service.exchangeShip(order.id,{version:order.version,case_id:caseId,...shipping,items:[line('A',1)]},actor);assert.equal(order.fulfillment,'processing');assert.equal(order.admin_cases[0].replacement_remaining[0].quantity,1);assert.equal(order.shipments[1].purpose,'exchange');
 order=await f.service.exchangeShip(order.id,{version:order.version,case_id:caseId,...shipping},actor);assert.equal(order.admin_cases[0].replacement_complete,true);await assert.rejects(f.service.exchangeShip(order.id,{version:order.version,case_id:caseId,...shipping},actor),{status:409});
 const replacementId=order.shipments[1].id;await f.advanceCase('closed','교환품 출고 완료, 기록 종결');await f.createCase('return',[line('A',1)],replacementId);assert.equal((await f.current()).admin_cases.length,2);
 const full=await f.ship();assert.equal(full.fulfillment,'shipped');const originals=full.shipments.filter(s=>s.purpose==='original');assert.equal(originals.flatMap(s=>s.items).reduce((n,x)=>n+x.quantity,0),5);
});
test('case creation concurrency and failed audit writes leave one complete transaction',async()=>{
 const f=await fixture(),shipped=await f.ship([line('A',1)]),input={version:shipped.version,kind:'return',shipment_id:shipped.shipments[0].id,items:[line('A',1)],reason:'검수 요청'};
 const results=await Promise.allSettled([f.service.createCase(shipped.id,input,actor),f.service.createCase(shipped.id,input,actor)]);assert.equal(results.filter(r=>r.status==='fulfilled').length,1);assert.equal((await f.current()).admin_cases.length,1);
 const before=await f.repo.get(shipped.id);f.sql.exec("CREATE TRIGGER reject_audit BEFORE INSERT ON shop_order_events BEGIN SELECT RAISE(ABORT,'audit unavailable'); END;");await assert.rejects(f.advanceCase('approved'));assert.equal((await f.repo.get(shipped.id)).customer_cipher,before.customer_cipher);
});
test('fulfillment mutation HTTP routes retain admin authentication, origin and session actor enforcement',async()=>{
 const f=await fixture(),handler=endpoint({service:f.service,repo:f.repo,sessionKey:secret,password:'unused',email:actor,enabled:false,clock}),cookie='__Host-nadaun-admin='+sessions(secret,clock).issue(actor,'admin',3600);
 async function call(action,body,headers={}){const res={setHeader(){},status(code){this.code=code;return this;},json(body){this.body=body;return this;}};await handler({url:'/api/orders?action='+action,method:'POST',body,headers:{origin:'https://order.nadaun.co',...headers}},res);return res;}
 for(const action of ['admin-ship','admin-shipment-update','admin-case-create','admin-case-update','admin-exchange-ship'])assert.equal((await call(action,{})).code,401);
 const shipped=await call('admin-ship',{id:f.order.id,version:1,...shipping,items:[line('A',1)],actor:'forged'},{cookie});assert.equal(shipped.code,200);assert.equal((await f.repo.events(f.order.id)).at(-1).actor,actor);
 const body={id:f.order.id,version:shipped.body.order.version,kind:'return',shipment_id:shipped.body.order.shipments[0].id,items:[line('A',1)],reason:'검수 사유',actor:'forged'};
 assert.equal((await call('admin-case-create',body,{cookie,origin:'https://evil.invalid'})).code,403);assert.equal((await call('admin-case-create',body,{cookie})).code,200);assert.equal((await f.current()).admin_cases[0].actor,actor);
});
test('coming-soon products cannot enter new orders or administrator reapproval despite numeric prices',async()=>{
 const f=await fixture();f.catalog.products[0].release_status='coming_soon';
 await assert.rejects(f.service.create(owner,'coming_soon_create_001',f.input),{status:409,message:'출시 예정 상품은 온라인 주문할 수 없습니다. 출시 일정과 구매 가능 여부를 상담으로 확인해주세요.'});
 const old=await f.repo.get(f.order.id);await f.repo.patch(old,{state:'REQUESTED'},'fixture','legacy_pending');await assert.rejects(f.service.approve(f.order.id,{version:2,stock_confirmed:true},actor),{status:409});assert.equal(f.calls.length,0);
});
test('Excel adds shipment and case ledgers while preserving explicit non-refund case labels',async()=>{
 const {adminService}=require('../../server/commerce/admin.cjs'),f=await fixture();await f.ship([line('A',2)]);await f.createCase('return',[line('A',1)]);await f.advanceCase('approved');await f.advanceCase('received');await f.advanceCase('closed','=internal note');
 const admin=adminService({db:f.db,service:f.service,dataKey:secret,clock}),output=await admin.export({format:'xlsx'}),ExcelJS=require('exceljs'),book=new ExcelJS.Workbook();await book.xlsx.load(output.body);
 assert.deepEqual(book.worksheets.map(w=>w.name),['안내와합계','주문결제','상품','증빙','처리이력','출고내역','반품교환']);
 const shipments=book.getWorksheet('출고내역');assert.equal(shipments.rowCount,2);assert.equal(shipments.getRow(2).getCell(12).value,2);
 const cases=book.getWorksheet('반품교환');assert.equal(cases.getRow(1).getCell(4).value,'기록상태(환불상태아님)');assert.equal(cases.getRow(2).getCell(4).value,'기록 종결');assert.equal(cases.getRow(2).getCell(13).value,'=internal note');assert.equal(cases.getRow(2).getCell(13).type,ExcelJS.ValueType.String);
 const csv=(await admin.export({format:'csv'})).body.toString();assert.ok(csv.includes('부분 출고'));assert.equal((await f.current()).state,'PAID');
});
test('exchange requires received goods and live verified payment; terminal cases cannot reopen',async()=>{
 const f=await fixture();await f.ship([line('A',1)]);await f.createCase('exchange',[line('A',1)]);let order=await f.current();await assert.rejects(f.service.exchangeShip(order.id,{version:order.version,case_id:order.admin_cases[0].id,...shipping},actor),{status:409});
 await f.advanceCase('approved');await f.advanceCase('received');order=await f.current();f.remote.status='PARTIAL_CANCELED';await assert.rejects(f.service.exchangeShip(order.id,{version:order.version,case_id:order.admin_cases[0].id,...shipping},actor),{status:409});assert.equal((await f.current()).state,'PAYMENT_REVIEW');assert.equal((await f.current()).shipments.length,1);
 const g=await fixture();await g.ship([line('A',1)]);await g.createCase();await g.advanceCase('rejected','고객 철회');await assert.rejects(g.advanceCase('approved'),{status:409});
});
