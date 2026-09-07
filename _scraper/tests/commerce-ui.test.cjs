const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../../assets/shop/commerce.js'),'utf8');
function runtime(overrides={}){
 const feedback={},request=[];let paymentRequest;
 function TossPayments(key){assert.equal(key,'test_ck_fixture');return {payment(options){assert.equal(options.customerKey,'ANONYMOUS');return {async requestPayment(value){paymentRequest=value;}};}};}TossPayments.ANONYMOUS='ANONYMOUS';
 const main={querySelector(){return null;}};
 const document={body:{dataset:{mode:'unit'}},querySelector(){return main;},createElement(){return {};},head:{append(script){assert.equal(script.src,'https://js.tosspayments.com/v2/standard');script.onload();}}};
 const context=vm.createContext({document,window:{TossPayments},URLSearchParams,console,location:{origin:'https://shop.nadaun.co'},fetch:async(url,options)=>{request.push({url,options});return{ok:true,json:async()=>({clientKey:'test_ck_fixture',mode:'test',orderId:'NS-fixture',amount:24500,orderName:'카메라'})};},...overrides});vm.runInContext(source,context);
 return {context,request,feedback,main,get paymentRequest(){return paymentRequest;}};
}
test('Toss checkout uses only the server-confirmed order and amount',async()=>{
 const r=runtime(),button={disabled:false};const card={querySelector(selector){return selector.includes('consent')?{checked:true}:r.feedback;}};
 await r.context.pay({id:'NS-fixture',quote_version:2,total:1},card,button);
 assert.equal(r.request.length,1);assert.deepEqual(JSON.parse(r.request[0].options.body),{id:'NS-fixture',quote_version:2});
 assert.equal(r.paymentRequest.amount.value,24500);assert.equal(r.paymentRequest.method,'CARD');assert.equal(r.paymentRequest.orderId,'NS-fixture');assert.equal(r.paymentRequest.successUrl,'https://shop.nadaun.co/orders.html?result=success');assert.equal(r.paymentRequest.failUrl,'https://shop.nadaun.co/orders.html?result=fail');
});
test('payment cannot begin before the customer confirms the final quote',async()=>{
 const r=runtime();await r.context.pay({id:'NS-fixture',quote_version:2},{querySelector(s){return s.includes('consent')?{checked:false}:r.feedback;}},{});assert.equal(r.request.length,0);assert.match(r.feedback.textContent,/동의/);
});
test('disabled checkout never collects a delivery address or loads the payment SDK',async()=>{
 const r=runtime({fetch:async()=>({ok:true,json:async()=>({ordersEnabled:false})})});let inserted=false;
 r.main.querySelector=selector=>selector==='.checkout-services'?{isConnected:true,before(){inserted=true;}}:null;
 await r.context.mountCheckout();assert.equal(inserted,false);assert.equal(r.paymentRequest,undefined);
});
test('order HTML escapes customer/product input and hides shipment actions for test payments',()=>{
 const r=runtime(),order={id:'NS-fixture',state:'PAID',payment_mode:'test',created_at:0,lines:[{id:'p',name:'<img src=x onerror=alert(1)>',option:'<script>x</script>',quantity:1,unit_price:100}],subtotal:100,shipping:4500,total:4600,customer:{name:'<svg onload=x>',phone:'000',address:'address'}};
 const html=r.context.orderCard(order,true);assert.ok(!html.includes('<img src=x'));assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<svg onload'));assert.match(html,/테스트 · 결제 완료/);assert.ok(!html.includes('commerce-shipping'));
 const customer=r.context.orderCard(order,false);assert.ok(!customer.includes('commerce-address'));assert.ok(!customer.includes('data-approve'));
});
