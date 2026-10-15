'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const crypto=require('node:crypto');
const {DatabaseSync}=require('node:sqlite');
const {adminDraftService}=require('../../server/commerce/admin-drafts.cjs');
const {protect}=require('../../server/commerce/security.cjs');

const secret='ae'.repeat(32),actor='operator@example.invalid';
const schema=fs.readFileSync('server/commerce/schema.sql','utf8');
const customer={name:'검증 고객',phone:'010-0000-0000',email:'buyer@example.invalid',postcode:'01234',address:'검증용 주소',address_detail:'검증실'};
function fixture(){
 let now=Date.parse('2026-10-15T03:00:00Z');
 const clock=()=>now,sql=new DatabaseSync(':memory:');sql.exec(schema);
 const db={async batch(statements){sql.exec('BEGIN');try{const result=statements.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return result;}catch(error){sql.exec('ROLLBACK');throw error;}},async query(s,p=[]){return (await this.batch([{sql:s,params:p}]))[0];}};
 const catalog={meta:{synced_at:new Date(now).toISOString(),revision:'draft-fixture'},redirects:{old:'camera'},products:[
  {id:'camera',name:'검증 카메라',kind:'purchase',status:'sale',price:20000,sale_price:18000,shipping_class:'standard',offers:[{source:'smartstore'}]},
  {id:'stand',name:'검증 스탠드',kind:'purchase',status:'sale',price:10000,sale_price:1,shipping_class:'heavy_stand',offers:[{source:'supplier'}]},
  {id:'inquiry',name:'금액 문의 상품',kind:'purchase',status:'inquiry',price:null,shipping_class:'standard',offers:[{source:'supplier'}]},
  {id:'coming',name:'출시 예정 상품',kind:'purchase',release_status:'coming_soon',status:'inquiry',price:null,offers:[]},
  {id:'rental',name:'검증 렌탈',kind:'rental',status:'sale'}
 ]};
 const details={camera:{options:[{name:'본체',additional_price:1000}]},stand:{},inquiry:{},coming:{},rental:{rental:{rates:[{label:'24시간',price:10000}]}}};
 const service=adminDraftService({db,catalog,detail:p=>details[p.id],dataKey:secret,clock});
 const purchase=overrides=>({kind:'purchase',customer:{...customer},items:[{id:'camera',option:'본체',quantity:2}],note:'내부 상담 원문',...overrides});
 const rental=overrides=>({kind:'rental',customer:{name:customer.name,phone:customer.phone},items:[{id:'rental',option:'24시간',quantity:2}],rental:{start_date:'2026-10-16',end_date:'2026-10-17',pickup_time:'12:00',return_time:'12:00'},...overrides});
 return {sql,db,catalog,details,service,purchase,rental,clock,advance:ms=>now+=ms};
}
const status=code=>error=>error?.status===code;

test('admin drafts store contact, internal notes and schedule encrypted without creating customer orders',async()=>{
 const f=fixture(),draft=await f.service.create(f.purchase({total:1,actor:'forged'}),actor);
 assert.match(draft.id,/^ND-/);assert.equal(draft.state,'draft');assert.equal(draft.version,0);
 assert.equal(draft.items[0].unit_price,19000);assert.equal(draft.subtotal,38000);assert.equal(draft.shipping,4500);assert.equal(draft.total,42500);
 assert.equal(draft.is_actual_order,false);assert.equal(draft.payment_available,false);assert.equal(draft.inventory_reserved,false);
 assert.equal(draft.created_by,actor);assert.ok(!('consent_version' in draft.customer));assert.ok(!('customer_hash' in draft));
 const row=(await f.db.query('SELECT * FROM shop_admin_drafts'))[0],serialized=JSON.stringify(row);
 for(const value of [customer.name,customer.phone,customer.email,customer.address,'내부 상담 원문'])assert.ok(!serialized.includes(value));
 const saved=protect(secret).decrypt(row.private_cipher);assert.deepEqual(saved.customer,customer);assert.equal(saved.note,'내부 상담 원문');
 assert.equal((await f.db.query('SELECT COUNT(*) AS n FROM shop_orders'))[0].n,0);
 assert.equal((await f.db.query('SELECT COUNT(*) AS n FROM shop_order_events'))[0].n,0);
 assert.deepEqual((await f.service.events(draft.id,actor)).map(event=>({...event})),[{actor,action:'draft_created',created_at:f.clock(),version:0}]);
 const normalized={kind:draft.kind,customer:draft.customer,note:draft.note,rental:null,lines:draft.items,subtotal:draft.subtotal,shipping:draft.shipping,total:draft.total};
 assert.equal(row.request_fingerprint,crypto.createHmac('sha256',Buffer.from(secret,'hex')).update(JSON.stringify(normalized)).digest('hex'));
 assert.notEqual(row.request_fingerprint,crypto.createHash('sha256').update(JSON.stringify(normalized)).digest('hex'));
});

test('draft creation retries are idempotent per administrator and reject changed request contents',async()=>{
 const f=fixture(),input=f.purchase({request_key:'draft_retry_request_0001'});
 const a=await f.service.create(input,actor),b=await f.service.create(input,actor);assert.equal(a.id,b.id);
 assert.equal((await f.service.events(a.id,actor)).length,1);
 await assert.rejects(f.service.create({...input,note:'다른 내용'},actor),status(409));
 const other=await f.service.create(input,'other@example.invalid');assert.notEqual(a.id,other.id);
 await assert.rejects(f.service.create({...input,request_key:'x'},actor),status(400));
});

test('purchase catalog options, quantities, availability and supplier prices are server validated',async()=>{
 const f=fixture();
 const stand=await f.service.create(f.purchase({items:[{id:'stand',option:'',quantity:2}]}),actor);
 assert.equal(stand.items[0].unit_price,10000);assert.equal(stand.total,27000);
 const redirected=await f.service.create(f.purchase({items:[{id:'old',option:'본체',quantity:1}]}),actor);assert.equal(redirected.items[0].id,'camera');
 for(const [items,code] of [
  [[{id:'camera',option:'없는 옵션',quantity:1}],409],
  [[{id:'camera',option:'본체',quantity:0}],400],
  [[{id:'camera',option:'본체',quantity:100}],400],
  [[{id:'camera',option:'본체',quantity:1.5}],400],
  [[{id:'camera',option:'본체',quantity:1},{id:'old',option:'본체',quantity:1}],400],
  [[{id:'coming',option:'',quantity:1}],409],
  [[{id:'rental',option:'24시간',quantity:1}],409],
  [[],400]
 ])await assert.rejects(f.service.create(f.purchase({items}),actor),status(code));
 f.details.camera.options[0].soldout=true;await assert.rejects(f.service.create(f.purchase(),actor),status(409));
 f.details.camera.options[0].soldout=false;f.details.camera.options_require_confirmation=true;await assert.rejects(f.service.create(f.purchase(),actor),status(409));
});

test('inquiry drafts keep null prices and cannot masquerade as reviewed quotes',async()=>{
 const f=fixture(),draft=await f.service.create(f.purchase({items:[{id:'inquiry',option:'',quantity:1}],prices:[{unit_price:1}]}),actor);
 assert.equal(draft.total,null);assert.equal(draft.items[0].unit_price,null);
 await assert.rejects(f.service.review(draft.id,{version:0},actor),status(409));
 const quote=await f.service.quote(draft.id,actor);assert.match(quote.body,/금액 미확정/);assert.match(quote.body,/견적 초안/);
});

test('rental quotes reuse exact schedule limits and require whole-period prices for review',async()=>{
 const f=fixture(),draft=await f.service.create(f.rental(),actor);assert.equal(draft.total,null);assert.equal(draft.shipping,0);
 const stored=protect(secret).decrypt((await f.db.query('SELECT private_cipher FROM shop_admin_drafts WHERE id=?',[draft.id]))[0].private_cipher);
 assert.equal(stored.rental.start_date,'2026-10-16');
 await assert.rejects(f.service.review(draft.id,{version:0},actor),status(409));
 const updated=await f.service.update(draft.id,f.rental({version:0,rental_prices:[{id:'rental',option:'24시간',unit_price:25000}]}),actor);
 assert.equal(updated.total,50000);const reviewed=await f.service.review(draft.id,{version:1},actor);assert.equal(reviewed.state,'reviewed');
 const quote=await f.service.quote(draft.id,actor);assert.match(quote.body,/전체 대여 기간 기준/);assert.match(quote.body,/2026-10-16 12:00/);
 await f.service.create(f.rental({rental:{start_date:'2026-10-16',end_date:'2026-10-30',pickup_time:'12:00',return_time:'12:00'}}),actor);
 for(const schedule of [
  {start_date:'2026-10-16',end_date:'2026-10-30',pickup_time:'12:00',return_time:'12:01'},
  {start_date:'2026-10-16',end_date:'2026-10-16',pickup_time:'12:00',return_time:'12:00'},
  {start_date:'2026-10-15',end_date:'2026-10-16',pickup_time:'11:59',return_time:'12:00'},
  {start_date:'2026-02-30',end_date:'2026-03-01',pickup_time:'12:00',return_time:'12:00'}
 ])await assert.rejects(f.service.create(f.rental({rental:schedule}),actor),status(400));
 for(const unit_price of [0,-1,1.5,100000001])await assert.rejects(f.service.create(f.rental({rental_prices:[{id:'rental',option:'24시간',unit_price}]}),actor),status(400));
 await assert.rejects(f.service.create(f.rental({items:[{id:'rental',option:'없는 요금',quantity:1}]}),actor),status(409));
});

test('review refreshes live catalog values and editing reviewed quotes requires a new review',async()=>{
 const f=fixture(),draft=await f.service.create(f.purchase(),actor);
 f.catalog.products[0].sale_price=20000;
 await assert.rejects(f.service.review(draft.id,{version:0},actor),status(409));
 const archived=await f.service.quote(draft.id,actor);assert.match(archived.body,/42,500원/);assert.match(archived.body,/저장 당시의 견적/);
 const updated=await f.service.update(draft.id,f.purchase({version:0}),actor);assert.equal(updated.total,46500);
 const reviewed=await f.service.review(draft.id,{version:1},actor);assert.equal(reviewed.state,'reviewed');assert.equal(reviewed.version,2);assert.equal(reviewed.reviewed_at,f.clock());
 await assert.rejects(f.service.review(draft.id,{version:2},actor),status(409));
 const changed=await f.service.update(draft.id,f.purchase({version:2,note:'다시 확인'}),actor);assert.equal(changed.state,'draft');assert.equal(changed.reviewed_at,null);
 assert.deepEqual((await f.service.events(draft.id,actor)).map(e=>e.action),['draft_created','draft_updated','draft_reviewed','draft_updated']);
});

test('review rechecks stale catalog, release status and elapsed rental pickup times',async()=>{
 const f=fixture(),draft=await f.service.create(f.purchase(),actor);
 f.catalog.products[0].release_status='coming_soon';await assert.rejects(f.service.review(draft.id,{version:0},actor),status(409));
 delete f.catalog.products[0].release_status;f.advance(49*3600000);
 await assert.rejects(f.service.create(f.purchase(),actor),status(503));await assert.rejects(f.service.review(draft.id,{version:0},actor),status(503));
 const r=fixture(),rental=await r.service.create(r.rental({rental_prices:[{id:'rental',option:'24시간',unit_price:10000}]}),actor);
 r.advance(25*3600000);r.catalog.meta.synced_at=new Date(r.clock()).toISOString();
 await assert.rejects(r.service.review(rental.id,{version:0},actor),status(400));
 assert.match((await r.service.quote(rental.id,actor)).body,/2026-10-16 12:00/);
 assert.match((await f.service.quote(draft.id,actor)).body,/현재 가격·재고·일정은 재검토/);
});

test('CAS allows only one concurrent update and one corresponding audit event',async()=>{
 const f=fixture(),draft=await f.service.create(f.purchase(),actor);
 const result=await Promise.allSettled([
  f.service.update(draft.id,f.purchase({version:0,note:'첫 담당자 수정'}),actor),
  f.service.update(draft.id,f.purchase({version:0,note:'다른 담당자 수정'}),'other@example.invalid')
 ]);
 assert.equal(result.filter(r=>r.status==='fulfilled').length,1);assert.equal(result.filter(r=>r.status==='rejected'&&r.reason.status===409).length,1);
 const events=await f.service.events(draft.id,actor);assert.equal(events.length,2);assert.equal(events[1].version,1);
 const current=await f.service.get(draft.id,actor);assert.equal(current.version,1);assert.equal(events[1].actor,current.updated_by);
 await assert.rejects(f.service.update(draft.id,f.purchase({version:0}),actor),status(409));
 await assert.rejects(f.service.review(draft.id,{version:'1'},actor),status(409));
});

test('audit insertion failure rolls back its draft mutation',async()=>{
 const f=fixture(),draft=await f.service.create(f.purchase(),actor);
 f.sql.exec("CREATE TRIGGER fail_draft_audit BEFORE INSERT ON shop_admin_draft_events WHEN NEW.action='draft_updated' BEGIN SELECT RAISE(ABORT,'fixture audit failure'); END;");
 await assert.rejects(f.service.update(draft.id,f.purchase({version:0,note:'저장되면 안 됨'}),actor),/fixture audit failure/);
 const saved=await f.service.get(draft.id,actor);assert.equal(saved.version,0);assert.equal(saved.note,'내부 상담 원문');assert.equal((await f.service.events(draft.id,actor)).length,1);
});

test('void records its encrypted reason and makes the draft immutable and unprintable',async()=>{
 const f=fixture(),draft=await f.service.create(f.purchase(),actor);
 await assert.rejects(f.service.void(draft.id,{version:0,reason:' '},actor),status(400));
 const voided=await f.service.void(draft.id,{version:0,reason:'고객 일정 재협의'},actor);assert.equal(voided.state,'voided');assert.equal(voided.void_reason,'고객 일정 재협의');
 const rows=await f.db.query('SELECT * FROM shop_admin_drafts');assert.ok(!JSON.stringify(rows).includes('고객 일정 재협의'));
 assert.ok(!JSON.stringify(await f.service.events(draft.id,actor)).includes('고객 일정 재협의'));
 for(const promise of [f.service.update(draft.id,f.purchase({version:1}),actor),f.service.review(draft.id,{version:1},actor),f.service.void(draft.id,{version:1,reason:'중복'},actor),f.service.quote(draft.id,actor)])await assert.rejects(promise,status(409));
 assert.equal((await f.service.get(draft.id,actor)).version,1);
});

test('all service entrypoints reject absent authenticated actors before reading data',async()=>{
 const f=fixture(),draft=await f.service.create(f.purchase(),actor);
 for(const action of [()=>f.service.products({kind:'purchase'}),()=>f.service.list({}),()=>f.service.get(draft.id),()=>f.service.create(f.purchase()),()=>f.service.update(draft.id,f.purchase({version:0})),()=>f.service.review(draft.id,{version:0}),()=>f.service.void(draft.id,{version:0,reason:'취소'}),()=>f.service.quote(draft.id),()=>f.service.events(draft.id)])await assert.rejects(action(),status(401));
 await assert.rejects(f.service.get(draft.id,'\n'),status(401));
});

test('list filters and pagination are parameterized and omit private details',async()=>{
 const f=fixture();
 for(let n=0;n<27;n++){await f.service.create(f.purchase({note:'비공개 메모 '+n}),actor);f.advance(1);}
 const rental=await f.service.create(f.rental(),actor);await f.service.void(rental.id,{version:0,reason:'일정 취소'},actor);
 const first=await f.service.list({},actor),second=await f.service.list({page:2},actor);assert.equal(first.total,28);assert.equal(first.drafts.length,25);assert.equal(first.pages,2);assert.equal(second.drafts.length,3);
 const filtered=await f.service.list({kind:'rental',state:'voided'},actor);assert.equal(filtered.total,1);assert.equal(filtered.drafts[0].id,rental.id);
 for(const draft of first.drafts){assert.deepEqual(Object.keys(draft.customer),['name']);assert.ok(!('note' in draft));assert.ok(!('void_reason' in draft));}
 assert.ok(!JSON.stringify(first).includes(customer.phone));assert.ok(!JSON.stringify(first).includes(customer.email));assert.ok(!JSON.stringify(first).includes('비공개 메모'));
 for(const input of [{state:"draft' OR 1=1--"},{kind:'all'},{page:'1 OR 1=1'},{page:0}])await assert.rejects(f.service.list(input,actor),status(400));
});

test('printable quotes escape source strings, omit notes and never imply payment or stock reservation',async()=>{
 const f=fixture();f.catalog.products[0].name='<script>source()</script> & 렌즈';
 const draft=await f.service.create(f.purchase({note:'내부비밀 <script>secret()</script>'}),actor);
 const quote=await f.service.quote(draft.id,actor);
 assert.equal(quote.type,'text/html; charset=utf-8');assert.match(quote.filename,/^nadaun-quote-ND-.*\.html$/);
 assert.ok(!quote.body.includes('<script>'));assert.ok(!quote.body.includes('secret()'));assert.match(quote.body,/&lt;script&gt;source\(\)&lt;\/script&gt;/);
 assert.match(quote.body,/재고 예약, 주문 접수 또는 결제 확정이 아닙니다/);assert.match(quote.body,/세금계산서가 아닙니다/);assert.match(quote.body,/고객에게 전송되지 않습니다/);
 assert.ok(!quote.body.includes('customer_hash'));assert.ok(!quote.body.includes('payment_key'));
 assert.equal((await f.service.get(draft.id,actor)).version,0);assert.equal((await f.service.events(draft.id,actor)).length,1);
});

test('additive schema is idempotent and leaves existing orders untouched',async()=>{
 const f=fixture();
 const draft=await f.service.create(f.purchase(),actor);f.sql.exec(schema);
 assert.equal((await f.service.get(draft.id,actor)).id,draft.id);
 const tables=await f.db.query("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'shop_admin_draft%'");assert.equal(tables.length,2);
 assert.equal((await f.service.events(draft.id,actor)).length,1);
});

test('invalid private fields, payload shapes and excess totals fail before storing a draft',async()=>{
 const f=fixture();
 for(const input of [null,[],f.purchase({kind:'gift'}),f.purchase({customer:{...customer,name:'x'}}),f.purchase({customer:{...customer,email:'bad'}}),f.purchase({customer:{...customer,postcode:'123'}}),f.purchase({note:'x'.repeat(2001)}),f.purchase({note:'bad\u0000note'}),f.purchase({rental:{}})])await assert.rejects(f.service.create(input,actor),status(400));
 f.catalog.products[0].sale_price=50000000;await assert.rejects(f.service.create(f.purchase(),actor),status(400));
 assert.equal((await f.service.list({},actor)).total,0);
 await assert.rejects(f.service.get('NS-not-a-draft',actor),status(400));
 await assert.rejects(f.service.get('ND-00000000-0000-0000-0000-000000000000',actor),status(404));
});

test('small product search bounds detail loading and exposes server options without inventing rental prices',async()=>{
 const f=fixture();
 let found=await f.service.products({kind:'purchase',q:'검증 카메라'},actor);assert.equal(found.total,1);assert.equal(found.products[0].price,18000);assert.deepEqual(found.products[0].options,[{name:'본체',additional_price:1000,disabled:false}]);
 found=await f.service.products({kind:'purchase'},actor);assert.ok(!found.products.some(p=>p.id==='coming'));
 found=await f.service.products({kind:'rental'},actor);assert.equal(found.products[0].price,null);assert.equal(found.products[0].options[0].name,'24시간');
 f.details.camera.options_require_confirmation=true;found=await f.service.products({kind:'purchase',q:'camera'},actor);assert.equal(found.products[0].disabled,true);
 f.details.camera.options_require_confirmation=false;f.details.camera.options[0].disabled=true;assert.equal((await f.service.products({kind:'purchase',q:'camera'},actor)).products[0].disabled,true);
 const catalog={meta:f.catalog.meta,products:Array.from({length:100},(_,n)=>({id:'item'+n,name:'검색 상품 '+n,kind:'purchase',status:'sale',price:10000,offers:[]}))};let detailReads=0;
 const service=adminDraftService({db:f.db,catalog,detail:()=>{detailReads++;return {};},dataKey:secret,clock:f.clock});
 found=await service.products({kind:'purchase'},actor);assert.equal(found.total,100);assert.equal(found.products.length,20);assert.equal(detailReads,20);
 await assert.rejects(f.service.products({kind:'all'},actor),status(400));await assert.rejects(f.service.products({kind:'purchase',q:'x'.repeat(101)},actor),status(400));
 f.advance(49*3600000);await assert.rejects(f.service.products({kind:'purchase'},actor),status(503));
});
