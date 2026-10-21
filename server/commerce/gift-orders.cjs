'use strict';
const {ShopError}=require('./security.cjs');
const {positive}=require('./pricing.cjs');

function text(value,max,label){
 if(value===undefined)return '';
 if(typeof value!=='string'||value.length>max||/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(value))throw new ShopError(400,label+'을 확인해주세요.');
 return value.trim();
}
// Saved supplier prices are deliberately not used: each request needs a fresh,
// explicit operator quote covering the requested printing and packaging.
function giftRequest(find,input,clock=()=>Date.now()){
 if(!input||typeof input!=='object'||Array.isArray(input)||typeof input.product_id!=='string'||!/^\d{1,12}$/.test(input.product_id))throw new ShopError(400,'기프트 상품번호를 확인해주세요.');
 const product=find?.(input.product_id);
 if(!product)throw new ShopError(404,'기프트 상품을 찾을 수 없습니다.');
 if(product.soldout)throw new ShopError(409,'입고 확인이 필요한 상품입니다. 상담을 이용해주세요.');
 if(!Number.isSafeInteger(input.quantity)||input.quantity<1||input.quantity>100000)throw new ShopError(400,'기프트 수량은 1~100,000개로 입력해주세요.');
 const gift={product_id:product.id,variant:text(input.variant,300,'색상·사양'),printing:text(input.printing,500,'인쇄 요청'),packaging:text(input.packaging,300,'포장 요청'),requested_date:text(input.requested_date,10,'희망 수령일'),notes:text(input.notes,1000,'추가 요청')};
 if(gift.requested_date){
  const date=Date.parse(gift.requested_date+'T00:00:00+09:00'),today=new Date(clock()+9*3600000).toISOString().slice(0,10);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(gift.requested_date)||!Number.isFinite(date)||new Date(date+9*3600000).toISOString().slice(0,10)!==gift.requested_date||gift.requested_date<today)throw new ShopError(400,'희망 수령일을 오늘 이후의 날짜로 입력해주세요.');
 }
 return {gift,lines:[{id:'gift-'+product.id,name:product.name,option:gift.variant,quantity:input.quantity,unit_price:null,image:product.image,shipping_class:'gift_quote',source_revision:'manual-gift-quote'}]};
}
function quoteGift(lines,input){
 if(input.gift_conditions_confirmed!==true)throw new ShopError(409,'공급처의 현재 판매 가능 여부·재고·인쇄·포장·납기와 최종 판매가를 확인해주세요.');
 if(!Array.isArray(input.gift_prices)||input.gift_prices.length!==lines.length)throw new ShopError(400,'모든 기프트 품목의 확정 단가를 입력해주세요.');
 const priced=lines.map((line,i)=>{
  const price=input.gift_prices[i];
  if(!price||price.id!==line.id||price.option!==line.option||!positive(price.unit_price))throw new ShopError(400,'기프트 품목과 부가세 포함 확정 단가를 확인해주세요.');
  return {...line,unit_price:price.unit_price};
 });
 const shipping=input.gift_shipping;
 if(!Number.isSafeInteger(shipping)||shipping<0||shipping>10000000)throw new ShopError(400,'부가세 포함 배송비를 확인해주세요.');
 const subtotal=priced.reduce((sum,line)=>sum+line.unit_price*line.quantity,0),total=subtotal+shipping;
 if(!positive(total))throw new ShopError(400,'주문 금액이 온라인 처리 범위를 넘었습니다. 상담을 이용해주세요.');
 return {lines:priced,subtotal,shipping,total};
}
module.exports={giftRequest,quoteGift};
