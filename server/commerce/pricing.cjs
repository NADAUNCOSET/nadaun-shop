'use strict';
const {ShopError}=require('./security.cjs');
function positive(value,max=100000000){return Number.isSafeInteger(value)&&value>0&&value<=max;}
function customerFields(raw){
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw new ShopError(400,'배송 정보를 확인해주세요.');
 const result={};
 for(const [key,min,max] of [['name',2,60],['phone',9,20],['postcode',5,5],['address',5,160],['address_detail',1,100]]){
  const value=typeof raw[key]==='string'?raw[key].trim():'';
  if(value.length<min||value.length>max||/[\x00-\x1f\x7f<>]/.test(value))throw new ShopError(400,'배송 정보를 확인해주세요.');
  result[key]=value;
 }
 if(!/^\d{5}$/.test(result.postcode)||!/^0[\d -]{8,19}$/.test(result.phone))throw new ShopError(400,'전화번호와 우편번호를 확인해주세요.');
 if(raw.consent!==true)throw new ShopError(400,'주문 처리에 필요한 개인정보 수집·이용 동의가 필요합니다.');
 result.consent_version='shop-order-2026-09-08';return result;
}
function quoteCatalog(catalog,detail,rows,clock=()=>Date.now()){
 const at=Date.parse(catalog.meta.synced_at);
 if(!Number.isFinite(at)||clock()-at>48*3600*1000||at>clock()+60000)throw new ShopError(503,'최신 상품 정보를 확인하고 있습니다. 잠시 후 다시 시도해주세요.');
 if(!Array.isArray(rows)||!rows.length||rows.length>30)throw new ShopError(400,'한 번에 1~30개 구성을 주문할 수 있습니다.');
 const products=new Map(catalog.products.map(p=>[p.id,p])),seen=new Set(),lines=[];
 for(const row of rows){
  if(!row||typeof row.id!=='string'||!positive(row.quantity,99)||typeof row.option!=='string'||row.option.length>300)throw new ShopError(400,'상품과 수량을 다시 선택해주세요.');
  const id=catalog.redirects[row.id]||row.id,p=products.get(id);
  if(!p||p.kind!=='purchase'||p.status==='soldout')throw new ShopError(409,'판매 상태가 변경된 상품이 있습니다. 장바구니를 확인해주세요.');
  const d=detail(p),options=d.options||[];
  if(d.options_require_confirmation)throw new ShopError(409,'옵션 구성을 상담으로 확인해야 하는 상품입니다.');
  const matches=options.filter(o=>o.name===row.option);
  if(options.length?matches.length!==1:row.option!=='')throw new ShopError(409,'상품 옵션이 변경되었습니다. 다시 선택해주세요.');
  const identity=JSON.stringify([id,row.option]);if(seen.has(identity))throw new ShopError(400,'같은 상품·옵션은 수량으로 합쳐주세요.');seen.add(identity);
  const own=p.offers.some(o=>['smartstore','imweb'].includes(o.source));
  const base=own?(p.sale_price??p.price):p.price,extra=matches[0]?.additional_price??0;
  if(!Number.isSafeInteger(extra))throw new ShopError(409,'옵션 금액을 확인해야 하는 상품입니다.');
  const unit=base===null?null:base+extra;
  if(unit!==null&&!positive(unit))throw new ShopError(409,'상품 금액을 확인해야 하는 상품입니다.');
  lines.push({id,name:p.name,option:row.option,quantity:row.quantity,unit_price:unit,image:p.image,shipping_class:p.shipping_class,source_revision:catalog.meta.revision});
 }
 const shipping=lines.some(p=>p.shipping_class==='heavy_stand')?7000:4500;
 const subtotal=lines.every(p=>p.unit_price!==null)?lines.reduce((n,p)=>n+p.unit_price*p.quantity,0):null;
 const total=subtotal===null?null:subtotal+shipping;
 if(total!==null&&!positive(total))throw new ShopError(400,'주문 금액이 온라인 처리 범위를 넘었습니다. 상담을 이용해주세요.');
 return {lines,subtotal,shipping,total};
}
module.exports={positive,customerFields,quoteCatalog};
