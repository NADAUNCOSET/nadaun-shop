const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(process.cwd(),'assets/shop/commerce.js'),'utf8');
function runtime(overrides={}){
 const feedback={},requests=[],sdkCalls=[],elements=[],main={querySelector(){return null;}};
 let paymentForm,close;
 const INIPayPro={requestPayment(form,callback){paymentForm=form;close=callback;sdkCalls.push('pay');}};
 function createElement(tag){const node={tag,isConnected:true,children:[],append(child){this.children.push(child);},remove(){this.isConnected=false;}};elements.push(node);return node;}
 const document={body:{dataset:{mode:'unit'},append(){}},querySelector(){return main;},createElement,head:{append(script){assert.equal(script.src,'https://paypro.inicis.com/std/payment/js/INIPayPro_v2.js');sdkCalls.push('load');script.onload();}}};
 const value={provider:'inicis',mode:'test',orderId:'NS-fixture',amount:24500,fields:{P_AMT:'24500',P_OID:'NS-fixture',P_NEXT_URL:'https://shop.nadaun.co/api/inicis-return',P_NOTI:'opaque-return-token'}};
 const context=vm.createContext({document,window:{INIPayPro},URLSearchParams,console,crypto:require('node:crypto').webcrypto,navigator:{userAgent:'Macintosh',maxTouchPoints:0},location:{origin:'https://shop.nadaun.co',search:''},history:{replaceState(){}},fetch:async(url,options)=>{requests.push({url,options});return{ok:true,json:async()=>value};},...overrides});vm.runInContext(source,context);
 return {context,requests,sdkCalls,elements,feedback,main,value,get paymentForm(){return paymentForm;},close:()=>close()};
}
const card=(r,checked=true)=>({querySelector:s=>s.includes('consent')?{checked}:r.feedback});
test('INICIS form uses only server-confirmed fields, not client totals; double clicks do not repeat',async()=>{
 const r=runtime(),button={disabled:false};await r.context.pay({id:'NS-fixture',quote_version:2,total:1},card(r),button);await r.context.pay({id:'NS-fixture',quote_version:2},card(r),button);
 assert.deepEqual(JSON.parse(r.requests[0].options.body),{id:'NS-fixture',quote_version:2,device:'WEB'});
 assert.equal(r.requests.length,1);assert.equal(r.paymentForm.children.find(p=>p.name==='P_AMT').value,'24500');assert.deepEqual(r.sdkCalls,['load','pay']);
 r.close();assert.equal(button.disabled,false);assert.equal(r.paymentForm.isConnected,false);assert.match(r.feedback.textContent,/닫았/);
});
test('payment requires final quote consent',async()=>{const r=runtime();await r.context.pay({id:'NS-fixture'},card(r,false),{});assert.equal(r.requests.length,0);assert.equal(r.sdkCalls.length,0);});
test('untrusted amount, provider, callback or malformed fields cannot open payment',async()=>{
 for(const mutate of [v=>v.amount=1,v=>v.provider='other',v=>v.fields.P_NEXT_URL='https://evil.invalid',v=>v.fields.bad='x',v=>v.fields.P_NOTI={x:1}]){const r=runtime();mutate(r.value);await r.context.pay({id:'NS-fixture'},card(r),{});assert.equal(r.paymentForm,undefined);}
});
test('mobile and touch iPad payments select MOBILE',()=>{
 for(const navigator of [{userAgent:'Android',maxTouchPoints:1},{userAgent:'iPhone',maxTouchPoints:1},{userAgent:'Macintosh',maxTouchPoints:5}])assert.equal(runtime({navigator}).context.deviceType(),'MOBILE');
 assert.equal(runtime().context.deviceType(),'WEB');
});
test('SDK errors remain retryable and never expose provider messages',async()=>{
 const r=runtime();let count=0;r.context.document.head.append=script=>{if(count++===0)script.onerror();else script.onload();};
 const button={};await r.context.pay({id:'NS-fixture'},card(r),button);assert.equal(button.disabled,false);assert.equal(r.paymentForm,undefined);await r.context.pay({id:'NS-fixture'},card(r),button);assert.ok(r.paymentForm);
});
test('disabled checkout does not collect delivery or business information or load PG scripts',async()=>{
 const r=runtime({fetch:async()=>({ok:true,json:async()=>({ordersEnabled:false})})});let inserted=false;r.main.querySelector=s=>s==='.checkout-services'?{isConnected:true,before(){inserted=true;}}:null;
 await r.context.mountCheckout();assert.equal(inserted,false);assert.equal(r.sdkCalls.length,0);
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
test('payment information page strips redirect query and never opens a free-payment demo',async()=>{
 let cleaned;const r=runtime({location:{origin:'https://shop.nadaun.co',search:'?result=success&paymentKey=secret'},history:{replaceState(a,b,path){cleaned=path;}}});const holder={};r.main.querySelector=()=>holder;await r.context.paymentTest();assert.equal(cleaned,'/payment-test.html');assert.equal(r.sdkCalls.length,0);assert.ok(!holder.innerHTML.includes('secret'));assert.match(holder.innerHTML,/오픈을 준비/);
});
