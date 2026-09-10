const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/shop/shipping.js','utf8').replaceAll('export ','')+'\n'+fs.readFileSync('assets/shop/cart.js','utf8').replace(/^import .*shipping\.js';\n/m,'').replaceAll('export ','');

async function render(rows,{products,details,checkout=true}={}){
 const main={innerHTML:'',querySelectorAll:()=>[]};let fetched=0;
 const context={
  document:{querySelector:()=>main,querySelectorAll:()=>[],dispatchEvent(){}},
  localStorage:{getItem:()=>JSON.stringify(rows)},window:{addEventListener(){}},
  CustomEvent:class{},setTimeout,clearTimeout,
  fetch:async()=>{fetched++;return {ok:true,json:async()=>details||{p:{options:[{name:'Black',additional_price:5000}],images:{main:['https://example.com/large.jpg']}}}}},
 };
 vm.createContext(context);vm.runInContext(source,context);
 await context.renderCart({meta:{revision:'test'},brands:[{id:'brand',name:'Test Brand'}],redirects:{old:'p'},products:products||[{id:'p',brand_id:'brand',name:'Camera <Test>',kind:'purchase',status:'sale',price:30000,sale_price:22000,image:'https://example.com/small.jpg',detail_bucket:'00',offers:[{source:'smartstore'}]}]},checkout);
 return {html:main.innerHTML,fetched};
}
test('checkout retains redirected products, selected option fees, quantities and detailed photography',async()=>{
 const {html,fetched}=await render([{id:'old',option:'Black',quantity:2}]);
 assert.equal(fetched,1);assert.match(html,/54,000/);assert.match(html,/class="order-total">58,500<small>원/);assert.match(html,/Camera &lt;Test&gt;/);
 assert.match(html,/src="https:\/\/example.com\/large.jpg"/);assert.match(html,/수량 <b>2<\/b>개/);
 assert.match(html,/href="\/item.html\?id=p"/);assert.ok(html.indexOf('렌탈 이용 방법')<html.indexOf('id="checkout-contact"'));
 assert.match(html,/온라인 결제 오픈 준비 중/);assert.doesNotMatch(html,/<input|<form/);
});
test('stale options are excluded and a partially known total is labelled as a subtotal',async()=>{
 const {html,fetched}=await render([{id:'p',option:'Black',quantity:1},{id:'p',option:'Old option',quantity:3}]);
 assert.equal(fetched,1);assert.match(html,/확인된 상품 소계/);assert.match(html,/27,000/);
 assert.match(html,/1개 구성<\/dd>/);assert.match(html,/판매 상태 또는 옵션이 변경/);
});
test('unavailable products do not appear to be a free order',async()=>{
 const {html}=await render([{id:'missing',option:'',quantity:1}]);
 assert.match(html,/금액 확인 필요/);assert.doesNotMatch(html,/>0<small>원/);assert.match(html,/상품 정보 확인 필요/);
});
test('cart keeps editable quantities, deletion and its checkout link',async()=>{
 const {html}=await render([{id:'p',option:'Black',quantity:2}],{checkout:false});
 assert.match(html,/data-quantity="0" value="2"/);assert.match(html,/data-remove="0"/);
 assert.match(html,/href="\/checkout.html"/);assert.doesNotMatch(html,/id="checkout-contact"/);
});
test('an empty selection has a working product discovery link and no total',async()=>{
 const {html,fetched}=await render([]);assert.equal(fetched,0);
 assert.match(html,/아직 담은 상품이 없습니다/);assert.match(html,/href="\/catalog.html"/);assert.doesNotMatch(html,/order-total/);
});
test('heavy stands charge 7000 once even with ordinary goods and several quantities',async()=>{
 const base={brand_id:'brand',kind:'purchase',status:'sale',price:30000,sale_price:30000,image:'https://example.test/p.jpg',detail_bucket:'00',offers:[]};
 const products=[{...base,id:'p',name:'C Stand',shipping_class:'heavy_stand'},{...base,id:'q',name:'Filter',shipping_class:'standard'}];
 const {html}=await render([{id:'p',option:'',quantity:2},{id:'q',option:'',quantity:1}],{products,details:{p:{options:[]},q:{options:[]}}});
 assert.match(html,/<dt>기본 배송비<\/dt><dd>7,000원/);
 assert.match(html,/class="order-total">97,000<small>원/);
});
test('sold-out heavy stands and rental items cannot raise purchase shipping',async()=>{
 const base={brand_id:'brand',kind:'purchase',status:'sale',price:30000,sale_price:30000,image:'https://example.test/p.jpg',detail_bucket:'00',offers:[]};
 const products=[{...base,id:'p',name:'Filter',shipping_class:'standard'},{...base,id:'q',name:'Sold out stand',shipping_class:'heavy_stand',status:'soldout'},{...base,id:'r',name:'Rental stand',shipping_class:'heavy_stand',kind:'rental'}];
 const {html}=await render([{id:'p',option:'',quantity:1},{id:'q',option:'',quantity:2},{id:'r',option:'',quantity:1}],{products,details:{p:{options:[]},q:{options:[]},r:{options:[]}}});
 assert.match(html,/<dt>기본 배송비<\/dt><dd>4,500원/);
 assert.match(html,/class="order-total">34,500<small>원/);
 assert.match(html,/2개 구성<\/dd>/);
});
test('saved sold-out or hidden variants are excluded from the checkout total',async()=>{
 for(const state of [{disabled:true},{soldout:true},{displayed:false},{supplier_status:'soldout'},{supplier_status:'unknown'}]){
  const {html}=await render([{id:'p',option:'Black',quantity:2}],{details:{p:{options:[{name:'Black',additional_price:5000,...state}]}}});
  assert.match(html,/판매 상태 또는 옵션이 변경/);assert.match(html,/금액 확인 필요/);assert.doesNotMatch(html,/54,000/);
 }
});
test('purchase controls label unavailable variants and refuse a stale forced selection',()=>{
 const handlers={},selection={value:'1',addEventListener(){},focus(){}},quantity={value:'1',addEventListener(){},reportValidity:()=>true};
 const slot={innerHTML:'',querySelector:s=>s==='select'?selection:s==='input'?quantity:{addEventListener:(_,fn)=>handlers[s]=fn}},toast={};let writes=0;
 const context={document:{querySelector:s=>s==='#purchase-options'?slot:toast,querySelectorAll:()=>[]},window:{addEventListener(){}},localStorage:{getItem:()=> '[]',setItem(){writes++}},setTimeout:()=>0,clearTimeout(){}};
 vm.createContext(context);vm.runInContext(source,context);
 context.mountPurchase({id:'p',kind:'purchase',status:'inquiry',price:163000,offers:[]},{options:[{name:'블랙',additional_price:0,supplier_status:'available'},{name:'화이트',additional_price:0,soldout:true,disabled:true}]});
 assert.match(slot.innerHTML,/<option value="1" disabled>화이트 · 품절<\/option>/);
 handlers['#add-cart']();assert.equal(writes,0);assert.match(toast.textContent,/판매 상태/);
 selection.value='0';handlers['#add-cart']();assert.equal(writes,1);
});
