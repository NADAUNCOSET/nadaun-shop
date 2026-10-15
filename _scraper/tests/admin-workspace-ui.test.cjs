'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../assets/shop/commerce.js'),'utf8');
function runtime(overrides={}){
 const saved=[];
 const context=vm.createContext({document:{body:{dataset:{mode:'unit'}},querySelector(){return{};}},location:{origin:'https://shop.nadaun.co'},URLSearchParams,crypto:require('node:crypto').webcrypto,localStorage:{getItem(){return null;},setItem(k,v){saved.push({k,v});}},...overrides});
 vm.runInContext(source,context);return {context,saved};
}
const plain=value=>JSON.parse(JSON.stringify(value));
const order=(changes={})=>({id:'NS-synthetic',kind:'purchase',state:'PAID',payment_mode:'live',created_at:0,version:1,fulfillment:'unfulfilled',customer:{name:'가상 고객',phone:'01000000000',address:'가상 주소'},lines:[{id:'fixture',name:'가상 장비',option:'',quantity:2,unit_price:10000}],subtotal:20000,shipping:4500,total:24500,...changes});
test('saved view settings and filters never retain search, customer, IDs or arbitrary labels',()=>{
 const r=runtime(),secret='synthetic-private';
 r.context.adminSavePreferences({columns:['customer','private-column'],density:'compact',layout:'cards',customer:secret,selection:[secret],presets:[{from:'2026-10-01',to:'2026-10-31',kind:'purchase',search:secret,name:secret,customer:secret,searchField:'customer',queue:'purchase-ready',unknown:secret}]});
 assert.equal(r.saved.length,1);assert.doesNotMatch(r.saved[0].v,/synthetic-private|private-column|selection/);
 const value=JSON.parse(r.saved[0].v);assert.deepEqual(value.columns,['order','customer']);assert.equal(value.presets[0].searchField,'customer');assert.equal(value.presets[0].queue,'purchase-ready');
});
test('malformed saved filters, impossible dates and unsupported enums cannot alter query behavior',()=>{
 const r=runtime();assert.deepEqual(plain(r.context.adminFilterMetadata(null)),{});
 const value=plain(r.context.adminFilterMetadata({from:'2026-02-30',to:'<script>',kind:'other',queue:'refund-all',mode:'operational',state:'PAID'}));assert.deepEqual(value,{mode:'operational',state:'PAID'});
 const p=r.context.adminPreferences({columns:[],layout:'evil',density:'evil',presets:Array(12).fill({from:'2026-01-01',to:'2026-12-31'})});assert.deepEqual(plain(p.columns),['order']);assert.equal(p.layout,'table');assert.equal(p.presets.length,8);
 const blocked=runtime({localStorage:{getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}}});assert.equal(blocked.context.adminReadPreferences().layout,'table');assert.equal(blocked.context.adminSavePreferences({}).layout,'table');
});
test('selected order rows escape content and retain an accessible selection label with hidden columns',()=>{
 const r=runtime(),o=order({id:'NS-<bad>',customer:{name:'<svg onload=x>'}}),prefs=r.context.adminPreferences({columns:['order','amount']});
 const html=r.context.adminTable([o],'',prefs,new Set([o.id]));assert.match(html,/is-selected/);assert.match(html,/NS-&lt;bad&gt; 주문 선택/);assert.match(html,/data-column="customer"[^>]*hidden/);assert.doesNotMatch(html,/<svg|NS-<bad>/);assert.match(html,/colspan="4"/);
});
test('workflow forms never offer manual in-transit or financial actions and require receipt confirmation',()=>{
 const r=runtime();for(const o of [order({kind:'rental'}),order({payment_mode:'test'}),order({state:'REQUESTED'})])assert.equal(r.context.adminWorkflowForm(o),'');
 const preparing=r.context.adminWorkflowForm(order());assert.match(preparing,/value="ready"/);assert.doesNotMatch(preparing,/value="in_transit"|value="delivered"|환불/);
 const shipped=order({fulfillment:'shipped',shipments:[{id:'s1',purpose:'original',items:[{id:'fixture',option:'',quantity:2}],carrier:'가상',tracking:'TEST123456'}]});
 const delivery=r.context.adminWorkflowForm(shipped);assert.match(delivery,/value="delivered"/);assert.match(delivery,/type="checkbox" required/);
 assert.match(r.context.adminShipmentSummary({...shipped,purchase_workflow:{stage:'delivered'}}),/관리자 수령 확인/);
});
test('order and transaction print templates have aligned columns and do not include internal notes',()=>{
 const r=runtime(),o=order({lines:[{id:'f',name:'<img src=x>',option:'<script>',quantity:2,unit_price:10000}],admin_note:'internal-secret',customer:{name:'가상',phone:'000',evidence:{corp_num:'business-secret'}}});
 const sheet=r.context.adminPrintDocument([o]),statement=r.context.adminPrintDocument([o],'statement');
 assert.match(sheet,/주문서/);assert.match(statement,/거래명세서/);assert.equal((sheet.match(/<th>/g)||[]).length,3);assert.equal((sheet.match(/<td>/g)||[]).length,3);assert.equal((statement.match(/<th>/g)||[]).length,4);assert.equal((statement.match(/<td>/g)||[]).length,4);assert.match(statement,/10,000원/);assert.match(statement,/상품 금액 20,000원 · 배송비 4,500원/);assert.match(statement,/주문 버전 1 · 출력/);
 for(const html of [sheet,statement]){assert.match(html,/세금계산서가 아닙니다/);assert.doesNotMatch(html,/<img|<script>|internal-secret|business-secret/);}
 assert.match(r.context.adminPrintDocument([order({total:null,lines:[{name:'가상',quantity:1,unit_price:null}]})]),/금액 확인 필요/);
});
test('print preview never calls print on load; only explicit print action does',async()=>{
 let prints=0,shown=0,removed=0;const button={},close={},frame={contentDocument:{fonts:{ready:Promise.resolve()}},contentWindow:{print(){prints++;}}};
 const dialog={dataset:{},querySelector(s){return s==='iframe'?frame:s==='[data-print-confirm]'?button:close;},showModal(){shown++;},close(){this.onclose();},remove(){removed++;}};
 const r=runtime({document:{body:{dataset:{mode:'unit'},append(){}},querySelector(){return{};},querySelectorAll(){return[];},createElement(){return dialog;}}});
 r.context.adminOpenPrintPreview('<p>synthetic</p>','주문서');await frame.onload();assert.equal(shown,1);assert.equal(prints,0);assert.match(dialog.innerHTML,/sandbox="allow-same-origin allow-modals"/);button.onclick();assert.equal(prints,1);close.onclick();assert.equal(removed,1);
});
test('invoice preview tolerates update rows without items, escapes errors and never renders its token',()=>{
 const r=runtime(),preview={valid:true,preview_token:'secret-preview-token',operations:[{index:0,rows:[2],id:'NS-a',operation:'update',carrier:'<script>',tracking:'<img>'}],totals:{orders:1,rows:1,items:0},errors:[]};
 const html=r.context.adminInvoicePreviewMarkup(preview);assert.match(html,/송장 수정/);assert.match(html,/검증 완료 · 실행 전/);assert.doesNotMatch(html,/<script>|<img>|secret-preview-token|undefined/);
 const failed=r.context.adminInvoicePreviewMarkup({...preview,valid:false,errors:[{rows:[2],error:'<bad>'}]});assert.doesNotMatch(failed,/data-invoice-apply/);assert.match(failed,/&lt;bad&gt;/);
 const done=r.context.adminInvoicePreviewMarkup(preview,{0:{ok:true,duplicate:true}});assert.match(done,/기존 처리 확인/);
});
test('invoice templates retain the exact schema and explicit version rather than customer information',()=>{
 const r=runtime(),csv=r.context.adminInvoiceTemplate([order()]);assert.ok(csv.startsWith('\ufeffoperation,order_id,version,shipment_id,carrier,tracking,item_id,option,quantity\r\n'));assert.match(csv,/"NS-synthetic","1"/);assert.doesNotMatch(csv,/가상 고객|01000000000/);assert.match(r.context.adminInvoiceTemplate([order({id:'=1+1'})]),/"'=1\+1"/);
});
test('draft purchase payload sends only catalog identities and quantities, never client price or order authority',()=>{
 const r=runtime(),value=r.context.adminDraftInput({kind:'purchase',name:' 가상 고객 ',phone:'01000000000',email:'',note:'내부 메모',total:'1',state:'PAID',consent:true},[{id:'p1',name:'임의 이름',option:'Black',quantity:'2',unit_price:1,source_revision:'fake'}],{id:'ND-fixture',version:4});
 assert.deepEqual(plain(value.items),[{id:'p1',option:'Black',quantity:2}]);assert.equal(value.customer.name,'가상 고객');assert.equal(value.id,'ND-fixture');assert.equal(value.version,4);assert.equal(value.rental,undefined);assert.equal(value.total,undefined);assert.equal(value.customer.consent,undefined);assert.equal(value.state,undefined);
});
test('draft rental prices remain null until all period unit prices are explicitly entered',()=>{
 const r=runtime(),values={kind:'rental',name:'가상',phone:'01000000000',start_date:'2026-12-01',end_date:'2026-12-02',pickup_time:'09:00',return_time:'18:00'},rows=[{id:'r1',quantity:1,option:'24시간',unit_price:null},{id:'r2',quantity:2,option:'',unit_price:''}];
 const unset=r.context.adminDraftInput(values,rows);assert.equal(unset.rental_prices,undefined);assert.deepEqual(plain(unset.rental),{start_date:'2026-12-01',end_date:'2026-12-02',pickup_time:'09:00',return_time:'18:00'});
 rows[0].unit_price='50000';assert.throws(()=>r.context.adminDraftInput(values,rows),/모든 상품/);rows[1].unit_price='60000';const set=r.context.adminDraftInput(values,rows);assert.deepEqual(plain(set.rental_prices),[{id:'r1',option:'24시간',unit_price:50000},{id:'r2',option:'',unit_price:60000}]);
 for(const quantity of [0,100,1.5,'bad'])assert.throws(()=>r.context.adminDraftInput(values,[{...rows[0],quantity}]),/1~99/);
 assert.throws(()=>r.context.adminDraftInput(values,[]),/1~30/);
});
test('draft search disables consultation-only products and unsafe options while escaping catalog text',()=>{
 const r=runtime(),html=r.context.adminDraftProducts([{id:'p',name:'<img onerror=x>',kind:'purchase',price:1000,disabled:true,notice:'<bad>',options:[{name:'Option'}]},{id:'r',name:'렌탈',kind:'rental',price:null,options:[{name:'<script>',disabled:true}]}]);
 const basic=r.context.adminDraftProducts([{id:'base',name:'가상 기본상품',kind:'purchase',price:1000,options:[{name:'',disabled:false}]}]);assert.match(basic,/<option value="" >기본 구성<\/option>/);
 assert.doesNotMatch(html,/<img|<script>|<bad>/);assert.equal((html.match(/disabled>추가/g)||[]).length,2);assert.match(html,/렌탈 · 기간 단가 직접 확인/);assert.match(html,/&lt;script&gt;/);
 const rows=r.context.adminDraftRows([{id:'r',name:'<svg>',option:'',quantity:1,unit_price:null}],'rental');assert.match(rows,/value="" min="1" max="100000000"/);assert.match(rows,/전체 기간 1개당 단가/);assert.doesNotMatch(rows,/<svg>|value="0"/);
});
test('automatic label UI distinguishes connection, printing and actual delivery without exposing keys',()=>{
 const r=runtime(),disabled=r.context.adminShippingPanel({enabled:false,message:'연결 대기',apiKey:'secret'});
 assert.match(disabled,/API 연결과 우리몰 계약 확인/);assert.doesNotMatch(disabled,/data-label-register|secret/);
 const html=r.context.adminShippingPanel({enabled:true,message:'연결됨',contracts:[{id:'contract',carrier_name:'<script>',center_name:'<img>'}]});assert.match(html,/선택 송장 인쇄/);assert.match(html,/이미 발급된 송장 재인쇄/);assert.doesNotMatch(html,/<script>|<img>/);
 assert.match(r.context.adminShipmentSummary(order({admin_shipping_label:{status:'printed',carrier:'로젠택배',tracking:'0123456789'}})),/발급 완료 · 집하 전/);
 assert.match(r.context.adminWorkflowForm(order({purchase_workflow:{stage:'delivered',delivery_source:'goodsflow'}})),/택배사에서 확인한 배송 완료/);
 const booked=order({state:'PAID',payment_mode:'live',admin_shipping_label:{status:'printed'},purchase_workflow:{stage:'ready'}});assert.equal(r.context.adminNext(booked),'택배사 집하 대기');assert.doesNotMatch(r.context.adminShipping(booked),/data-shipment-create/);
});
