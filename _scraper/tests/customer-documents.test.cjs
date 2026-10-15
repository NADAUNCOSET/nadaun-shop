const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {DatabaseSync}=require('node:sqlite');
const {repository,orderService}=require('../../server/commerce/orders.cjs');
const {documentService}=require('../../server/commerce/documents.cjs');
const {toss}=require('../../server/commerce/toss.cjs');
const {hash,sessions,protect}=require('../../server/commerce/security.cjs');
const {endpoint}=require('../../server/commerce/http.cjs');
const secret='ab'.repeat(32),owner=hash('buyer-one'),other=hash('buyer-two');
const business={kind:'tax_invoice',corp_num:'1234567891',corp_name:'검증용 상호',ceo_name:'검증 대표',address:'서울시 검증로 123',biz_type:'도소매',biz_class:'촬영장비',email:'test@example.invalid'};
async function fixture(){
 let now=Date.parse('2026-10-08T00:00:00Z'),state='DONE',url='https://test.popbill.com/App/API?T=fixture',prints=0,issues=0;const clock=()=>now;
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync('server/commerce/schema.sql','utf8'));
 const db={async batch(statements){sql.exec('BEGIN');try{const out=statements.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return out;}catch(e){sql.exec('ROLLBACK');throw e;}},async query(s,p=[]){return (await this.batch([{sql:s,params:p}]))[0];}};
 const repo=repository(db,clock),catalog={meta:{synced_at:new Date(now).toISOString()},redirects:{},products:[{id:'p1',name:'카메라',kind:'purchase',status:'inquiry',price:10000,offers:[],shipping_class:'standard'}]};
 const adapter=toss({SHOP_PAYMENT_MODE:'test',SHOP_TOSS_CLIENT_KEY:'test_ck_fixture',SHOP_TOSS_SECRET_KEY:'test_sk_fixture'},undefined,clock);let remote;
 const payment={...adapter,async approve(auth,row){remote={provider:'toss',orderId:row.id,paymentKey:'fixture_key',totalAmount:row.total,currency:'KRW',status:'DONE',method:'BANK',cashReceipt:{present:false,issued:false}};return {...remote};},async get(){return {...remote,status:state};}};
 const invoice={mode:'test',async lookup(){return issues?{issued:true,approval_number:'202610081234567890123456',nts_status:'pending'}:null;},async issue(){issues++;return this.lookup();},async customerPrint(){prints++;return url;}};
 const documents=documentService({db,repo,dataKey:secret,payment,invoice,clock}),service=orderService({repo,catalog,detail:()=>({}),dataKey:secret,payment,documents,invoiceEnabled:true,clock});
 const customer={name:'검증고객',phone:'010-0000-0000',postcode:'01234',address:'서울시 검증로 123',address_detail:'테스트동',consent:true};
 let row=await service.create(owner,'customer_docs_fixture',{customer,items:[{id:'p1',option:'',quantity:1}],evidence:business});row=await service.approve(row.id,{version:row.version,stock_confirmed:true});const started=await service.start(row.id,owner,row.quote_version);
 const callback={orderId:row.id,amount:String(row.total),paymentKey:'fixture_key',token:new URL(started.request.successUrl).searchParams.get('token')};
 return {sql,repo,service,documents,clock,id:row.id,invoice,payment,get prints(){return prints;},get issues(){return issues;},setState(v){state=v;},setURL(v){url=v;},async pay(){return service.acceptReturn(callback);}};
}
test('customer document operations require ownership and a paid order before provider access',async()=>{
 const f=await fixture();await assert.rejects(f.service.customerDocument(f.id,other,true),{status:404});await assert.rejects(f.service.customerDocument(f.id,owner,true),{status:409});assert.equal(f.prints,0);
 await f.pay();const refreshed=await f.service.customerDocument(f.id,owner);assert.equal(refreshed.document.status,'issued');assert.equal(refreshed.customer,undefined);assert.equal(refreshed.admin_note,undefined);
 assert.equal((await f.service.customerDocument(f.id,owner,true)).url,'https://test.popbill.com/App/API?T=fixture');assert.equal(f.issues,1);
 await f.service.customerDocument(f.id,owner);assert.equal(f.issues,1);
});
test('recipient print rejects refunds, unsafe URLs and changed invoice identity without issuing again',async()=>{
 const f=await fixture();await f.pay();f.setState('CANCELED');await assert.rejects(f.service.customerDocument(f.id,owner,true),{status:409});assert.equal(f.prints,0);f.setState('DONE');
 for(const url of ['http://test.popbill.com/App/API','https://www.popbill.com.evil.invalid/','https://user@www.popbill.com/','https://www.popbill.com:444/']){f.setURL(url);await assert.rejects(f.service.customerDocument(f.id,owner,true),{status:503});}
 f.invoice.lookup=async()=>({issued:true,approval_number:'wrong'});await assert.rejects(f.service.customerDocument(f.id,owner,true),{status:409});assert.equal(f.issues,1);
});
test('customer document API requires same origin and a customer cookie; admin cookie is insufficient',async()=>{
 const f=await fixture();await f.pay();const handler=endpoint({service:f.service,repo:f.repo,sessionKey:secret,password:'unused',clock:f.clock});
 async function call({action='document-print',origin='https://shop.nadaun.co',cookie=''}={}){const res={setHeader(){},status(v){this.code=v;return this;},json(v){this.value=v;return this;}};await handler({url:'/api/orders?action='+action,method:'POST',headers:{origin,cookie},body:{id:f.id}},res);return res;}
 assert.equal((await call()).code,401);assert.equal((await call({cookie:'__Host-nadaun-admin='+sessions(secret,f.clock).issue('owner','admin',60)})).code,401);
 const cookie='__Host-nadaun-customer='+sessions(secret,f.clock).issue('buyer-one','customer',60);
 assert.equal((await call({cookie,origin:'https://other.invalid'})).code,403);assert.equal((await call({cookie})).code,200);assert.equal((await call({cookie,action:'document-refresh'})).code,200);
 assert.equal(f.issues,1);
});
