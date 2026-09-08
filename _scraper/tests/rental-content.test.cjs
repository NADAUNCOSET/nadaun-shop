const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const rental=require('../../assets/shop/rental-content.js');
const catalog=JSON.parse(fs.readFileSync('data/catalog/catalog.json','utf8'));
const details=JSON.parse(fs.readFileSync('data/catalog/rental-details.json','utf8'));

test('every rental has matching visible periods and packing before any specification images',()=>{
 const rows=catalog.products.filter(p=>p.kind==='rental');
 assert.equal(Object.keys(details).length,rows.length);
 for(const p of rows){
  const d=details[p.id],html=rental.render(p,d,{brand:p.brand_id});
  assert.match(html,/id="rental-components"/);assert.match(html,/id="rental-use"/);
  assert.doesNotMatch(html,/구매 안내|구매 · 배송|옵션과 수량을 선택한 뒤 주문서|undefined/);
  assert.ok(html.includes('kind=rental'));
  if(d.images.detail?.length)assert.ok(html.indexOf('id="rental-components"')<html.indexOf('id="rental-specifications"'));
  for(const rate of d.rental.rates)assert.ok(html.includes(Number(rate.price).toLocaleString('ko-KR')));
 }
});

test('unknown periods remain explicit and studio guidance never uses equipment pickup instructions',()=>{
 for(const p of catalog.products.filter(p=>p.kind==='rental')){
  const html=rental.render(p,details[p.id],{brand:p.brand_id});
  if(!p.rental.period)assert.match(html,/표시 요금의 적용 기간은 예약 전 상담/);
  if(p.rental.service==='studio'){
   assert.match(html,/스튜디오 이용 안내/);assert.doesNotMatch(html,/픽업 장소/);
  }
 }
});

test('rental source content is escaped and unsafe image URLs cannot render',()=>{
 const p={id:'rental-1',name:'<script>bad</script>',brand_id:'sony',image:'javascript:alert(1)',rental:{price:10000,period:null}};
 const d={images:{main:[],detail:['javascript:alert(2)']},rental:{rates:[],components:[{name:'<img onerror=bad>',quantity:1}],notes:['<script>bad</script>'],period_confirmation_required:true}};
 const html=rental.render(p,d,{brand:'<bad>'});
 assert.doesNotMatch(html,/<script>|javascript:|<img onerror/);
 assert.match(html,/&lt;script&gt;/);assert.match(html,/대여기간 확인/);
});

test('rental periods are included in the server-rendered product page before JavaScript',()=>{
 const handler=require('../../api/product.js');
 const p=catalog.products.find(p=>p.kind==='rental'&&p.rental.rate_count===2);
 const res={setHeader(){},status(code){this.code=code;return this;},end(body){this.body=body;return this;}};
 handler({method:'GET',url:'/item.html?id='+p.id},res);
 assert.equal(res.code,200);assert.match(res.body,/12시간/);assert.match(res.body,/24시간/);assert.match(res.body,/포함 구성품/);
});

test('rental detail uses the source gallery and falls back to its own cached image on failure',()=>{
 const p=catalog.products.find(p=>p.kind==='rental'&&details[p.id].images.main?.length);
 const d=details[p.id],html=rental.render(p,d,{brand:p.brand_id});
 assert.ok(html.includes('src="'+d.images.main[0].replace(/&/g,'&amp;')+'"'));
 const events={},img={dataset:{rentalFallback:p.image},src:d.images.main[0],complete:false,
  getAttribute(){return this.src;},addEventListener(name,fn){events[name]=fn;}};
 rental.mount({querySelector(){return img;},querySelectorAll(){return [];}});
 events.error();assert.equal(img.src,p.image);
 events.error();assert.equal(img.src,p.image);
});
