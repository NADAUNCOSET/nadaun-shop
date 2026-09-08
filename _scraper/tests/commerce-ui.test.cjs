const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(process.cwd(),'assets/shop/commerce.js'),'utf8');
function runtime(overrides={}){
 const feedback={},request=[],sdkCalls=[],elements=[];let paymentRequest,widgetAmount;
 const main={querySelector(){return null;}};
 function TossPayments(key){sdkCalls.push(['key',key]);return {widgets(options){assert.equal(options.customerKey,'ANONYMOUS');return {
  async setAmount(value){widgetAmount=value;sdkCalls.push(['amount',value]);},
  async renderPaymentMethods(value){sdkCalls.push(['methods',value]);return {destroy(){}};},
  async renderAgreement(value){sdkCalls.push(['agreement',value]);return {destroy(){}};},
  async requestPayment(value){paymentRequest=value;sdkCalls.push(['request',value]);}
 };}};}TossPayments.ANONYMOUS='ANONYMOUS';
 const document={body:{dataset:{mode:'unit'}},querySelector(){return main;},createElement(){const node={isConnected:true,remove(){this.isConnected=false;}};elements.push(node);return node;},head:{append(script){assert.equal(script.src,'https://js.tosspayments.com/v2/standard');sdkCalls.push(['load']);script.onload();}}};
 const context=vm.createContext({document,window:{TossPayments},URLSearchParams,console,crypto:require('node:crypto').webcrypto,location:{origin:'https://shop.nadaun.co',search:''},history:{replaceState(){}},fetch:async(url,options)=>{request.push({url,options});return{ok:true,json:async()=>({clientKey:'test_gck_fixture',mode:'test',orderId:'NS-fixture',amount:24500,orderName:'카메라'})};},...overrides});vm.runInContext(source,context);
 return {context,request,sdkCalls,elements,feedback,main,get paymentRequest(){return paymentRequest;},get widgetAmount(){return widgetAmount;}};
}
function card(r,checked=true){return {querySelector(selector){if(selector.includes('consent'))return {checked};if(selector==='.commerce-actions')return {before(){}};return r.feedback;}};}
function previewHolder(r,checked=true){const button={},consent={checked},amount={};return {id:'preview-fixture',isConnected:true,button,consent,amount,querySelector(s){if(s==='[data-preview-pay]')return button;if(s==='[data-preview-consent]')return consent;if(s==='[data-preview-amount]')return amount;return r.feedback;}};}
test('order widgets use the server-confirmed amount before rendering methods and agreement',async()=>{
 const r=runtime(),button={disabled:false};await r.context.pay({id:'NS-fixture',quote_version:2,total:1},card(r),button);
 assert.deepEqual(JSON.parse(r.request[0].options.body),{id:'NS-fixture',quote_version:2});assert.equal(r.widgetAmount.value,24500);assert.equal(r.widgetAmount.currency,'KRW');
 assert.equal(r.paymentRequest,undefined);assert.deepEqual(r.sdkCalls.map(x=>x[0]),['load','key','amount','methods','agreement']);
 await button.onclick();assert.equal(r.paymentRequest.orderId,'NS-fixture');assert.equal(r.paymentRequest.successUrl,'https://shop.nadaun.co/orders.html?result=success');assert.equal(r.paymentRequest.failUrl,'https://shop.nadaun.co/orders.html?result=fail');assert.equal(r.paymentRequest.amount,undefined);assert.equal(r.paymentRequest.customerEmail,undefined);
 await button.onclick();assert.equal(r.sdkCalls.filter(x=>x[0]==='request').length,1);
});
test('payment cannot begin before the customer confirms the final quote',async()=>{
 const r=runtime();await r.context.pay({id:'NS-fixture',quote_version:2},card(r,false),{});assert.equal(r.request.length,0);assert.match(r.feedback.textContent,/동의/);
});
test('disabled checkout without a cart never collects an address or loads widgets',async()=>{
 const r=runtime({fetch:async()=>({ok:true,json:async()=>({ordersEnabled:false})})});let inserted=false;
 r.main.querySelector=selector=>selector==='.checkout-services'?{isConnected:true,before(){inserted=true;}}:null;
 await r.context.mountCheckout();assert.equal(inserted,false);assert.equal(r.sdkCalls.length,0);
});
test('order HTML escapes input and hides shipment actions for test payments',()=>{
 const r=runtime(),order={id:'NS-fixture',state:'PAID',payment_mode:'test',created_at:0,lines:[{id:'p',name:'<img src=x onerror=alert(1)>',option:'<script>x</script>',quantity:1,unit_price:100}],subtotal:100,shipping:4500,total:4600,customer:{name:'<svg onload=x>',phone:'000',address:'address'}};
 const html=r.context.orderCard(order,true);assert.ok(!html.includes('<img src=x'));assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<svg onload'));assert.match(html,/테스트 · 결제 완료/);assert.ok(!html.includes('commerce-shipping'));
 const customer=r.context.orderCard(order,false);assert.ok(!customer.includes('commerce-address'));assert.ok(!customer.includes('data-approve'));
});
test('pre-contract preview uses only the public widget test key, without order or approval API calls',async()=>{
 const r=runtime(),holder=previewHolder(r);await r.context.startPreview(holder,49000);
 assert.equal(r.sdkCalls.find(x=>x[0]==='key')[1],'test_gck_docs_Ovk5rk1EwkEbP0W43n07xlzm');assert.equal(r.widgetAmount.value,49000);assert.equal(holder.amount.textContent,'49,000원');
 await holder.button.onclick();assert.equal(r.request.length,0);assert.match(r.paymentRequest.orderId,/^NDPREVIEW_[a-f0-9]{32}$/);assert.match(r.paymentRequest.orderName,/주문 아님/);assert.equal(r.paymentRequest.successUrl,'https://shop.nadaun.co/payment-test.html?result=success');assert.equal(r.paymentRequest.customerName,undefined);
 const html=r.context.previewMarkup('preview');assert.match(html,/실제 금액이 청구되지/);assert.match(html,/주문 접수·배송도 진행되지/);assert.ok(!html.includes('name="address"'));
});
test('preview requires explicit test acknowledgement and prevents double clicks',async()=>{
 const r=runtime(),holder=previewHolder(r,false);await r.context.startPreview(holder);
 await holder.button.onclick();assert.equal(r.paymentRequest,undefined);assert.match(r.feedback.textContent,/테스트임/);
 holder.consent.checked=true;await holder.button.onclick();await holder.button.onclick();assert.equal(r.sdkCalls.filter(x=>x[0]==='request').length,1);
});
test('unknown and excessive cart amounts do not open preview widgets',async()=>{
 for(const amount of [0,NaN,-5,1.5,100000001]){const r=runtime(),holder=previewHolder(r);await r.context.startPreview(holder,amount);assert.equal(holder.button.disabled,true);assert.equal(r.sdkCalls.length,0);}
});
test('legacy individual keys are rejected by the widget renderer',async()=>{
 const r=runtime();await assert.rejects(r.context.mountWidget({clientKey:'test_ck_fixture',amount:1000},{id:'x'},{},{}),/결제수단/);assert.equal(r.sdkCalls.length,0);
});
test('preview return strips query data and never treats a success URL as a paid order',async()=>{
 let cleaned;const r=runtime({location:{origin:'https://shop.nadaun.co',search:'?result=success&paymentKey=secret-return&message=%3Cimg%3E'},history:{replaceState(a,b,path){cleaned=path;}}});const status={},holder=previewHolder(r);
 r.main.querySelector=s=>s==='#preview-result'?status:holder;await r.context.paymentTest();
 assert.equal(cleaned,'/payment-test.html');assert.match(status.textContent,/결제 승인은 요청하지 않았으며/);assert.ok(!status.textContent.includes('secret-return'));assert.equal(r.request.length,0);
});
test('SDK failures remain retryable without rendering a fake payment success',async()=>{
 const r=runtime();r.context.window.TossPayments=Object.assign(()=>({widgets:()=>({setAmount:async()=>{},renderPaymentMethods:async()=>{throw Error('load');},renderAgreement:async()=>({destroy(){}})})}),{ANONYMOUS:'ANONYMOUS'});
 const holder=previewHolder(r);await r.context.startPreview(holder);assert.equal(holder.button.disabled,true);assert.match(r.feedback.textContent,/새로고침/);assert.equal(r.paymentRequest,undefined);
});
test('canceled payment re-enables the button and does not expose raw provider errors',async()=>{
 const r=runtime();r.context.window.TossPayments=Object.assign(()=>({widgets:()=>({setAmount:async()=>{},renderPaymentMethods:async()=>({destroy(){}}),renderAgreement:async()=>({destroy(){}}),requestPayment:async()=>{throw {code:'PAY_PROCESS_CANCELED',message:'secret-detail'};}})}),{ANONYMOUS:'ANONYMOUS'});
 const holder=previewHolder(r);await r.context.startPreview(holder);await holder.button.onclick();assert.equal(holder.button.disabled,false);assert.match(r.feedback.textContent,/중단/);assert.ok(!r.feedback.textContent.includes('secret-detail'));
});

test('checkout mounts a test widget with its complete cart total while keeping delivery collection off',async()=>{
 const r=runtime({fetch:async()=>({ok:true,json:async()=>({ordersEnabled:false})})});
 const holder=previewHolder(r),state={},link={firstChild:{}},step={};let inserted;
 r.context.document.createElement=tag=>tag==='section'?holder:{remove(){}};
 const summary={dataset:{previewAmount:'54500'},querySelector:s=>s==='.summary-state'?state:link};
 const services={isConnected:true,before(node){inserted=node;}};
 r.main.querySelector=s=>s==='.checkout-services'?services:s==='.order-summary'?summary:s==='#checkout-payment-preview'?inserted:s==='.selection-steps li:last-child'?step:null;
 await r.context.mountCheckout();assert.equal(inserted.id,'checkout-payment-preview');assert.equal(r.widgetAmount.value,54500);assert.match(state.textContent,/테스트 결제/);assert.equal(link.href,'#checkout-payment-preview');
 assert.equal(r.elements.some(n=>n.id==='delivery-form'),false);await r.context.mountCheckout();assert.equal(r.sdkCalls.filter(x=>x[0]==='methods').length,1);
});
