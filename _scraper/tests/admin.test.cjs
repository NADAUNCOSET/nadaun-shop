const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {DatabaseSync}=require('node:sqlite');
const {adminService,filters,csv}=require('../../server/commerce/admin.cjs');
const {repository,orderService}=require('../../server/commerce/orders.cjs');
const {protect,sessions,hash,passwordHash}=require('../../server/commerce/security.cjs');
const {documentService}=require('../../server/commerce/documents.cjs');
const {endpoint}=require('../../server/commerce/http.cjs');
const secret='ab'.repeat(32),clock=()=>Date.parse('2026-10-09T00:00:00Z'),cipher=protect(secret);
function fixture(count=2){
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync('server/commerce/schema.sql','utf8'));
 const db={async batch(statements){sql.exec('BEGIN');try{const out=statements.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return out;}catch(error){sql.exec('ROLLBACK');throw error;}},async query(s,p=[]){return (await this.batch([{sql:s,params:p}]))[0];}};
 const repo=repository(db,clock),documents=documentService({db,repo,dataKey:secret,payment:null,clock});
 const service=orderService({repo,catalog:{},detail:()=>{},dataKey:secret,payment:null,documents,clock});
 const admin=adminService({db,service,dataKey:secret,clock});
 for(let i=0;i<count;i++){
  const id='NS-fixture_'+String(i).padStart(6,'0'),created=Date.parse('2026-02-01T00:00:00+09:00')+i;
  const customer={name:i===0?'=HYPERLINK("https://evil.invalid")':'검증용 고객',phone:'010-0000-0000',postcode:'01234',address:'검증 주소',address_detail:'검증 상세',evidence:{kind:'tax_invoice',corp_num:'1234567891',corp_name:'샘플 상호',email:'test@example.invalid'}};
  const receipt={provider:'inicis',orderId:id,paymentKey:'payment_fixture_'+i,totalAmount:14500,currency:'KRW',status:'DONE',method:'BANK',approvalDate:'2026-02-01'};
  sql.prepare('INSERT INTO shop_orders(id,customer_hash,request_key,fingerprint,state,customer_cipher,lines_json,subtotal,shipping,total,payment_key,payment_provider,payment_receipt_cipher,paid_at,payment_mode,confirm_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)').run(id,hash('test'),String(i),'fingerprint','PAID',cipher.encrypt(customer),JSON.stringify([{id:'p1',name:'샘플 장비',option:'블랙',quantity:1,unit_price:10000}]),10000,4500,14500,receipt.paymentKey,'inicis',cipher.encrypt(receipt),created+1000,'live','nonce'+i,created,created+1000);
  sql.prepare('INSERT INTO shop_order_events VALUES(?,?,?,?,?,?)').run('event'+i,id,'payment','payment_done',created+1000,0);
  sql.prepare('INSERT INTO shop_documents(order_id,kind,status,result_cipher,created_at,updated_at) VALUES(?,?,?,?,?,?)').run(id,'tax_invoice',i===1?'queued':'issued',cipher.encrypt({approval_number:'12345',nts_status:'pending'}),created,created);
 }
 return {sql,db,repo,service,admin};
}
test('KST annual range is inclusive across UTC year edges; impossible dates are rejected',()=>{
 const f=filters({from:'2026-01-01',to:'2026-12-31'},clock);assert.equal(f.start,Date.parse('2025-12-31T15:00:00Z'));assert.equal(f.end,Date.parse('2026-12-31T15:00:00Z'));
 for(const input of [{from:'2026-02-30'},{from:'2025-01-01',to:'2026-12-31'},{mode:'bad'},{page:'0'},{state:"PAID' OR 1=1"}])assert.throws(()=>filters(input,clock),{status:400});
});
test('paged UI and complete annual export include orders beyond the old 100 row limit',async()=>{
 const f=fixture(1203),list=await f.admin.list({});assert.equal(list.summary.orders,1203);assert.equal(list.orders.length,25);assert.equal(list.pages,49);
 assert.equal((await f.admin.list({page:49})).orders.length,3);
 const output=await f.admin.export({format:'xlsx'}),ExcelJS=require('exceljs'),book=new ExcelJS.Workbook();await book.xlsx.load(output.body);
 assert.deepEqual(book.worksheets.map(w=>w.name),['안내와합계','주문결제','상품','증빙','처리이력']);assert.equal(book.getWorksheet('주문결제').rowCount,1204);assert.equal(book.getWorksheet('상품').rowCount,1204);assert.equal(book.getWorksheet('처리이력').rowCount,1204);
 assert.equal(book.getWorksheet('주문결제').getRow(1204).getCell(8).value,'=HYPERLINK("https://evil.invalid")');assert.equal(book.getWorksheet('주문결제').getRow(1204).getCell(8).type,ExcelJS.ValueType.String);assert.equal(book.getWorksheet('주문결제').getRow(1204).getCell(10).value,'01234');
 assert.equal(book.getWorksheet('주문결제').getRow(1204).getCell(15).value,14500);
});
test('test payments never enter default summaries and refund amounts are not fabricated',async()=>{
 const f=fixture(4);f.sql.prepare("UPDATE shop_orders SET payment_mode='test' WHERE id=?").run('NS-fixture_000003');
 f.sql.prepare("UPDATE shop_orders SET state='CANCELED' WHERE id=?").run('NS-fixture_000000');f.sql.prepare("UPDATE shop_orders SET state='PAYMENT_REVIEW' WHERE id=?").run('NS-fixture_000001');
 const list=await f.admin.list({});assert.equal(list.summary.orders,3);assert.equal(list.summary.approvedTotal,43500);assert.equal(list.summary.canceledOriginalTotal,14500);assert.equal(list.summary.paymentReview,1);
 assert.equal((await f.admin.list({mode:'test'})).summary.orders,1);
 const output=await f.admin.export({format:'xlsx'}),ExcelJS=require('exceljs'),book=new ExcelJS.Workbook();await book.xlsx.load(output.body);const data=book.getWorksheet('주문결제');for(let i=2;i<=data.rowCount;i++)assert.equal(data.getRow(i).getCell(17).value,null);
});
test('payment-period selection finds a previous-year order paid in the selected year and legacy audit fallback',async()=>{
 const f=fixture();f.sql.prepare('UPDATE shop_orders SET created_at=? WHERE id=?').run(Date.parse('2025-12-31T14:59:59Z'),'NS-fixture_000000');
 f.sql.prepare('UPDATE shop_orders SET paid_at=NULL WHERE id=?').run('NS-fixture_000001');
 assert.equal((await f.admin.list({basis:'created'})).summary.orders,1);assert.equal((await f.admin.list({basis:'paid'})).summary.orders,2);
 assert.equal((await f.admin.list({document:'queued'})).summary.orders,1);assert.equal((await f.admin.list({search:"' OR 1=1"})).summary.orders,0);
});
test('CSV blocks spreadsheet formula injection and preserves leading-zero identifiers',async()=>{
 const value=csv([['=cmd',' +SUM(A1)','@evil','\ttext','01234',-25,'한글,"따옴표"']]);assert.match(value,/"'=cmd"/);assert.match(value,/"'01234"/);assert.match(value,/"-25"/);
 const output=await fixture().admin.export({format:'csv'});assert.equal(output.body[0],239);assert.ok(output.body.toString().includes("'=HYPERLINK"));
});
test('admin login/export works before public checkout is enabled; customer and anonymous access stay blocked',async()=>{
 const f=fixture(),password=await passwordHash('test-only administrator password'),handler=endpoint({service:f.service,repo:f.repo,adminService:f.admin,password,sessionKey:secret,enabled:false,clock});
 async function call(action,method='GET',body,headers={}){const res={headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.code=n;return this;},json(v){this.body=v;return this;},send(v){this.body=v;return this;}};await handler({url:'/api/orders?action='+action,method,body,headers:{origin:'https://shop.nadaun.co',...headers}},res);return res;}
 assert.equal((await call('config')).body.adminEnabled,true);assert.equal((await call('config')).body.ordersEnabled,false);
 assert.equal((await call('admin-export&format=csv')).code,401);assert.equal((await call('admin-export&format=csv','GET',null,{cookie:'__Host-nadaun-customer='+sessions(secret,clock).issue('customer','customer')})).code,401);
 const logged=await call('login','POST',{password:'test-only administrator password'});assert.equal(logged.code,200);const cookie=logged.headers['Set-Cookie'].split(';')[0];
 const exported=await call('admin-export&format=csv','GET',null,{cookie});assert.equal(exported.code,200);assert.equal(exported.headers['Cache-Control'],'no-store');assert.match(exported.headers['Content-Disposition'],/attachment/);
 assert.equal((await call('create','POST',{}, {cookie})).code,503);
 assert.equal((await call('login','POST',{password:'test-only administrator password'},{origin:'https://evil.invalid'})).code,403);
 await assert.rejects(f.service.retryDocument('NS-fixture_000001'),{status:503});
});
