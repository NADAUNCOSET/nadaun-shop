const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/shop/cart.js','utf8').replaceAll('export ','');

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
 assert.equal(fetched,1);assert.match(html,/54,000/);assert.match(html,/Camera &lt;Test&gt;/);
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
