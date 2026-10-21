const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(process.cwd(),'assets/shop/commerce.js'),'utf8');
function runtime(overrides={}){
 const feedback={},requests=[],sdkCalls=[],elements=[],main={querySelector(){return null;}};
 let paymentForm,close;
 const TossPayments=key=>({payment({customerKey}){assert.equal(customerKey,'ANONYMOUS');assert.equal(key,'test_ck_fixture');return {requestPayment(request){paymentForm=request;sdkCalls.push('pay');return new Promise((resolve,reject)=>{close=()=>reject(Error('closed'));});}};}});TossPayments.ANONYMOUS='ANONYMOUS';
 function createElement(tag){const node={tag,isConnected:true,children:[],append(child){this.children.push(child);},remove(){this.isConnected=false;}};elements.push(node);return node;}
 const document={body:{dataset:{mode:'unit'},append(){}},querySelector(){return main;},createElement,head:{append(script){assert.equal(script.src,'https://js.tosspayments.com/v2/standard');sdkCalls.push('load');script.onload();}}};
 const value={provider:'toss',mode:'test',clientKey:'test_ck_fixture',orderId:'NS-fixture',amount:24500,request:{method:'CARD',amount:{currency:'KRW',value:24500},orderId:'NS-fixture',orderName:'test',successUrl:'https://shop.nadaun.co/api/toss-return?token=opaque',failUrl:'https://shop.nadaun.co/orders.html?result=closed'}};
 const context=vm.createContext({document,window:{TossPayments},URL,URLSearchParams,console,crypto:require('node:crypto').webcrypto,navigator:{userAgent:'Macintosh',maxTouchPoints:0},location:{origin:'https://shop.nadaun.co',search:''},history:{replaceState(){}},fetch:async(url,options)=>{requests.push({url,options});return{ok:true,json:async()=>value};},...overrides});vm.runInContext(source,context);
 return {context,requests,sdkCalls,elements,feedback,main,value,get paymentForm(){return paymentForm;},close:()=>close()};
}
const card=(r,checked=true)=>({querySelector:s=>s.includes('consent')?{checked}:r.feedback});
const paymentOrder={id:'NS-fixture',quote_version:2,total:24500};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('Toss uses only the approved server amount; double clicks cannot repeat checkout',async()=>{
 const r=runtime(),button={};const pending=r.context.pay(paymentOrder,card(r),button);await tick();await r.context.pay(paymentOrder,card(r),button);
 assert.deepEqual(JSON.parse(r.requests[0].options.body),{id:'NS-fixture',quote_version:2,device:'WEB'});assert.equal(r.requests.length,1);assert.equal(r.paymentForm.amount.value,24500);assert.deepEqual(r.sdkCalls,['load','pay']);r.close();await pending;assert.equal(button.disabled,false);assert.match(r.feedback.textContent,/닫혔/);
});
test('payment requires final quote consent',async()=>{const r=runtime();await r.context.pay(paymentOrder,card(r,false),{});assert.equal(r.requests.length,0);assert.equal(r.sdkCalls.length,0);});
test('tampered amount, order, provider, key or callback cannot open payment',async()=>{
 for(const mutate of [v=>v.amount=1,v=>v.request.amount.value=1,v=>v.orderId='foreign',v=>v.provider='other',v=>v.clientKey='live_ck_fixture',v=>v.request.successUrl='https://evil.invalid/',v=>v.request.failUrl='https://evil.invalid/']){const r=runtime();mutate(r.value);await r.context.pay(paymentOrder,card(r),{});assert.equal(r.paymentForm,undefined);}
});
test('mobile and touch iPad payments select MOBILE',()=>{
 for(const navigator of [{userAgent:'Android',maxTouchPoints:1},{userAgent:'iPhone',maxTouchPoints:1},{userAgent:'Macintosh',maxTouchPoints:5}])assert.equal(runtime({navigator}).context.deviceType(),'MOBILE');assert.equal(runtime().context.deviceType(),'WEB');
});
test('SDK errors remain retryable and never expose provider messages',async()=>{
 const r=runtime();let count=0;r.context.document.head.append=script=>{if(count++===0)script.onerror();else script.onload();};const button={};await r.context.pay(paymentOrder,card(r),button);assert.equal(button.disabled,false);assert.equal(r.paymentForm,undefined);const pending=r.context.pay(paymentOrder,card(r),button);await tick();assert.ok(r.paymentForm);r.close();await pending;
});
test('disabled checkout does not collect delivery or business information or load PG scripts',async()=>{
 const r=runtime({fetch:async()=>({ok:true,json:async()=>({ordersEnabled:false})})});let inserted=false;r.main.querySelector=s=>s==='.checkout-services'?{isConnected:true,before(){inserted=true;}}:null;
 await r.context.mountCheckout();assert.equal(inserted,false);assert.equal(r.sdkCalls.length,0);
});
test('admin readiness separates enabled administration from pending customer payments and invoices',()=>{
 const r=runtime();
 const pending=r.context.adminReadiness({adminEnabled:true,paymentProvider:'toss',ordersEnabled:false,rentalRequestsEnabled:false,taxInvoiceEnabled:false});
 assert.match(pending,/토스페이먼츠/);assert.equal((pending.match(/오픈 준비 중/g)||[]).length,3);assert.match(pending,/발급 연결 준비 중/);assert.doesNotMatch(pending,/접수 가능|<strong>발급 연결됨/);
 const enabled=r.context.adminReadiness({paymentProvider:'toss',ordersEnabled:true,rentalRequestsEnabled:true,giftRequestsEnabled:true,taxInvoiceEnabled:true});
 assert.match(enabled,/토스페이먼츠/);assert.equal((enabled.match(/접수 가능/g)||[]).length,3);assert.match(enabled,/<strong>발급 연결됨/);
 assert.match(r.context.adminReadiness({paymentProvider:'<script>bad</script>',ordersEnabled:'true'}),/확인 필요/);assert.doesNotMatch(r.context.adminReadiness({ordersEnabled:'true'}),/접수 가능/);
});
test('tax invoice option is only available when server reports a configured issuer',()=>{
 const r=runtime();assert.ok(!r.context.evidenceForm(false).includes('<option value="tax_invoice">'));assert.match(r.context.evidenceForm(true),/<option value="tax_invoice">/);assert.match(r.context.evidenceForm(true),/type="email"/);assert.match(r.context.evidenceForm(true),/소득공제 \/ 지출증빙/);
});
test('document state escapes approval text and separates issue from NTS acceptance',()=>{
 const r=runtime();const html=r.context.documentCard({kind:'tax_invoice',status:'issued',approval_number:'<img src=x>',nts_status:'pending'});assert.ok(!html.includes('<img'));assert.match(html,/국세청 전송 결과는 확인 중/);assert.match(r.context.documentCard({kind:'cash_receipt',purpose:'business',status:'issued'}),/지출증빙/);
});
test('order HTML hides private business data and test shipment actions',()=>{
 const r=runtime(),order={id:'NS-fixture',state:'PAID',payment_mode:'test',created_at:0,lines:[{id:'p',name:'<img src=x onerror=alert(1)>',option:'<script>x</script>',quantity:1,unit_price:100}],subtotal:100,shipping:4500,total:4600,customer:{name:'<svg onload=x>',phone:'000',address:'address',evidence:{corp_num:'secret-business-id'}}};
 const html=r.context.orderCard(order,true);assert.ok(!html.includes('<img src=x'));assert.ok(!html.includes('<script>'));assert.ok(!html.includes('commerce-shipping'));const customer=r.context.orderCard(order);assert.ok(!customer.includes('secret-business-id'));assert.ok(!customer.includes('commerce-address'));
});
test('test payment page strips sensitive redirect query and fails closed on invalid merchant configuration',async()=>{
 let cleaned;const r=runtime({location:{origin:'https://shop.nadaun.co',search:'?result=success&paymentKey=secret'},history:{replaceState(a,b,path){cleaned=path;}}});const holder={};r.main.querySelector=()=>holder;await r.context.paymentTest();assert.equal(cleaned,'/payment-test.html');assert.equal(r.sdkCalls.length,0);assert.ok(!holder.innerHTML.includes('secret'));assert.match(holder.innerHTML,/테스트 연결을 확인/);
});

test('order submission includes only checked cart lines and strips selection metadata',()=>{
 const rows=[{id:'legacy',option:'',quantity:2},{id:'unchecked',quantity:3,selected:false},{id:'checked',option:'Black',quantity:1,selected:true}];
 const r=runtime({localStorage:{getItem:()=>JSON.stringify(rows)}});
 assert.deepEqual(JSON.parse(JSON.stringify(r.context.checkoutItems())),[{id:'legacy',option:'',quantity:2},{id:'checked',option:'Black',quantity:1}]);
});

test('rental admin shows requested visits and contact without shipping fields or a fabricated total',()=>{
 const r=runtime(),order={id:'NS-rental',kind:'rental',state:'REQUESTED',created_at:0,lines:[{id:'r1',name:'조명',option:'24시간',quantity:2,unit_price:null}],subtotal:null,shipping:0,total:null,fulfillment:'unfulfilled',rental:{start_date:'2026-10-10',end_date:'2026-10-11',pickup_time:'09:15',return_time:'10:45'},customer:{name:'예약자<private>',phone:'01000000000'}};
 const html=r.context.orderCard(order,true);assert.match(html,/2026-10-10 09:15/);assert.match(html,/2026-10-11 10:45/);assert.match(html,/예약자&lt;private&gt;/);assert.match(html,/전체 기간 1개당 확정 요금/);assert.doesNotMatch(html,/배송 정보 확인|commerce-shipping|운송장|배송 0원|undefined/);
 assert.doesNotMatch(r.context.orderCard(order),/01000000000|예약자&lt;private&gt;/);
});
test('rental-only requests cannot display a payment button before PG activation',()=>{
 const r=runtime();vm.runInContext('checkoutPaymentOpen=false',r.context);const html=r.context.customerActions({kind:'rental',state:'APPROVED',total:90000});assert.doesNotMatch(html,/data-pay/);assert.match(html,/온라인 결제 연결을 준비 중/);
});

test('admin table separates next actions and safely renders hostile customer/product strings',()=>{
 const r=runtime(),o={id:'NS-test',kind:'purchase',state:'PAID',payment_mode:'live',fulfillment:'unfulfilled',created_at:0,lines:[{id:'a',name:'<img src=x>',option:'',quantity:2,unit_price:10}],customer:{name:'<svg onload=x>'},subtotal:20,shipping:0,total:20};
 const html=r.context.adminTable([o],'NS-test');assert.doesNotMatch(html,/<svg|<img src=x/);assert.match(html,/aria-expanded="true"/);assert.match(html,/출고·운송장 입력/);assert.match(html,/선택 수량 출고 처리/);
 assert.equal(r.context.adminNext({...o,kind:'rental',fulfillment:'processing'}),'방문 반납 확인');assert.equal(r.context.adminNext({...o,payment_mode:'test'}),'테스트 결제');assert.equal(r.context.adminNext({...o,admin_cases:[{status:'received'}]}),'반품·교환 확인');
});
test('shipment quantities exclude exchange re-shipments and protect legacy completed deliveries',()=>{
 const r=runtime(),o={kind:'purchase',fulfillment:'processing',lines:[{id:'a',option:'Black',quantity:3}],shipments:[{id:'s1',purpose:'original',items:[{id:'a',option:'Black',quantity:1}]},{id:'s2',purpose:'exchange',items:[{id:'a',option:'Black',quantity:1}]}]};
 assert.equal(r.context.remainingShipmentItems(o)[0].quantity,2);
 assert.equal(r.context.remainingShipmentItems({...o,shipments:[],fulfillment:'shipped'}).length,0);
 assert.equal(r.context.caseRemaining({...o,admin_cases:[{shipment_id:'s1',status:'closed',items:[{id:'a',option:'Black',quantity:1}]}]},o.shipments[0]).length,0);
 assert.equal(r.context.caseRemaining({...o,admin_cases:[{shipment_id:'s1',status:'rejected',items:[{id:'a',option:'Black',quantity:1}]}]},o.shipments[0])[0].quantity,1);
});
test('internal notes and cancellations stay out of customer cards and payment-stage notes are disabled',()=>{
 const r=runtime(),o={id:'NS-fixture',state:'PAYMENT_PENDING',kind:'purchase',created_at:0,lines:[],subtotal:0,shipping:0,total:0,admin_note:{text:'internal-secret<script>'},admin_cancellation:{reason:'private-reason'}};
 const own=r.context.orderCard(o);assert.doesNotMatch(own,/internal-secret|private-reason|data-admin-note/);
 const admin=r.context.orderCard(o,true);assert.match(admin,/internal-secret&lt;script&gt;/);assert.match(admin,/결제 진행 중에는 메모를 변경할 수 없습니다/);assert.doesNotMatch(admin,/data-cancel-request/);
});
test('customer shipment summary exposes shipment facts without internal claim reasons or actors',()=>{
 const r=runtime(),o={kind:'purchase',shipments:[{id:'s1',purpose:'original',carrier:'로젠',tracking:'12345678',items:[{id:'a',name:'Camera',quantity:1}],actor:'internal-actor'}],admin_cases:[{reason:'private-case-reason'}]};
 const html=r.context.customerShipments(o);assert.match(html,/12345678/);assert.match(html,/Camera 1개/);assert.doesNotMatch(html,/internal-actor|private-case-reason/);
});

test('shipped orders retain returns and tracking correction after PG cancellation without enabling new shipments',()=>{
 const r=runtime(),base={kind:'purchase',payment_mode:'live',fulfillment:'processing',lines:[{id:'p',name:'상품',option:'',quantity:2}],shipments:[{id:'s',purpose:'original',items:[{id:'p',name:'상품',option:'',quantity:1}],carrier:'택배',tracking:'1234567'}]};
 for(const state of ['PAID','PAYMENT_REVIEW','CANCELED']){const html=r.context.adminShipping({...base,state});assert.match(html,/data-case-create=/);assert.match(html,/data-shipment-update=/);if(state!=='PAID')assert.doesNotMatch(html,/data-shipment-create/);}
});
