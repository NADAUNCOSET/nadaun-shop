(function(root,factory){
 const value=factory();
 if(typeof module==='object'&&module.exports)module.exports=value;
 else root.NadaunGiftPricing=value;
})(typeof globalThis==='object'?globalThis:this,function(){
 'use strict';
 const integer=(n,min,max)=>Number.isSafeInteger(n)&&n>=min&&n<=max;
 function validate(p){
  if(!p||!/^\w{16}$/.test(p.revision||'')||!integer(p.minimum_quantity,1,100000)||p.vat_basis_points!==1000||!Number.isFinite(Date.parse(p.observed_at))||!Array.isArray(p.options)||!p.options.length||p.options.length>100)throw Error('상품 가격표를 확인해주세요.');
  const ids=new Set();
  for(const o of p.options){
   if(!o||!/^\w{16}$/.test(o.id||'')||ids.has(o.id)||typeof o.label!=='string'||o.label.length>1000||!Array.isArray(o.tiers)||!o.tiers.length||o.tiers.length>50)throw Error('상품 옵션을 확인해주세요.');
   ids.add(o.id);let last=0;
   for(const t of o.tiers){if(!integer(t.minimum_quantity,1,100000)||t.minimum_quantity<=last||!integer(t.unit_price_ex_vat,1,100000000))throw Error('상품 수량별 단가를 확인해주세요.');last=t.minimum_quantity;}
  }
  return p;
 }
 function calculate(p,quantity,optionId){
  validate(p);
  if(!integer(quantity,1,100000))throw Error('수량은 1~100,000개로 입력해주세요.');
  const option=p.options.find(o=>o.id===optionId);
  if(!option)throw Error('상품 옵션을 다시 선택해주세요.');
  if(quantity<p.minimum_quantity||quantity<option.tiers[0].minimum_quantity)return {status:'below_minimum',minimum_quantity:Math.max(p.minimum_quantity,option.tiers[0].minimum_quantity),option_id:option.id,option_label:option.label,quantity};
  const tier=option.tiers.filter(t=>t.minimum_quantity<=quantity).at(-1);
  const subtotal=tier.unit_price_ex_vat*quantity;
  // The source rounds VAT on the complete goods subtotal, not each item.
  const total=Math.floor((subtotal*110+50)/100),vat=total-subtotal;
  if(!Number.isSafeInteger(total)||total>100000000)throw Error('큰 금액의 주문은 별도 견적을 요청해주세요.');
  return {status:'estimated',revision:p.revision,observed_at:p.observed_at,option_id:option.id,option_label:option.label,quantity,minimum_quantity:tier.minimum_quantity,unit_price_ex_vat:tier.unit_price_ex_vat,subtotal_ex_vat:subtotal,vat,total_including_vat:total,shipping_included:false,requires_confirmation:true};
 }
 return {validate,calculate};
});
