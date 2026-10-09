'use strict';
const {ShopError}=require('./security.cjs');
function rentalSchedule(raw,clock=()=>Date.now()){
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw new ShopError(400,'대여 시작·종료 날짜와 방문 시간을 입력해주세요.');
 const result={};
 for(const key of ['start_date','end_date']){const value=raw[key];if(typeof value!=='string'||!/^20\d{2}-\d{2}-\d{2}$/.test(value))throw new ShopError(400,'대여 날짜를 확인해주세요.');result[key]=value;}
 for(const key of ['pickup_time','return_time']){const value=raw[key];if(typeof value!=='string'||!/^([01]\d|2[0-3]):[0-5]\d$/.test(value))throw new ShopError(400,'수령·반납 방문 시간을 정확히 입력해주세요.');result[key]=value;}
 function instant(day,time){const ms=Date.parse(day+'T'+time+':00+09:00');if(!Number.isFinite(ms)||new Date(ms+9*3600000).toISOString().slice(0,16)!==day+'T'+time)throw new ShopError(400,'달력에 있는 날짜와 방문 시간을 입력해주세요.');return ms;}
 result.pickup_at=instant(result.start_date,result.pickup_time);result.return_at=instant(result.end_date,result.return_time);
 if(result.pickup_at<clock())throw new ShopError(400,'수령 방문 일시가 지났습니다. 새 일정을 선택해주세요.');
 if(result.return_at<=result.pickup_at)throw new ShopError(400,'반납 방문 일시는 수령 방문 일시보다 늦어야 합니다.');
 return result;
}
function rentalCustomer(raw){
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw new ShopError(400,'예약자 정보를 확인해주세요.');
 const name=typeof raw.name==='string'?raw.name.trim():'',phone=typeof raw.phone==='string'?raw.phone.trim():'';
 if(name.length<2||name.length>60||/[\x00-\x1f\x7f<>]/.test(name)||!/^0[\d -]{8,19}$/.test(phone))throw new ShopError(400,'예약자 이름과 연락처를 확인해주세요.');
 if(raw.consent!==true)throw new ShopError(400,'렌탈 일정 접수에 필요한 개인정보 수집·이용 동의가 필요합니다.');
 return {name,phone,consent_version:'shop-rental-request-2026-10-09'};
}
function rentalQuote(catalog,detail,rows,prices=null,clock=()=>Date.now()){
 const at=Date.parse(catalog.meta.synced_at);if(!Number.isFinite(at)||clock()-at>48*3600000||at>clock()+60000)throw new ShopError(503,'최신 렌탈 정보를 확인하고 있습니다. 잠시 후 다시 시도해주세요.');
 if(!Array.isArray(rows)||!rows.length||rows.length>30)throw new ShopError(400,'한 번에 1~30개 렌탈 구성을 요청할 수 있습니다.');
 if(prices!==null&&(!Array.isArray(prices)||prices.length!==rows.length))throw new ShopError(400,'모든 렌탈 상품의 전체 기간 단가를 확인해주세요.');
 const products=new Map(catalog.products.map(p=>[p.id,p])),seen=new Set(),lines=[];
 for(const [index,row] of rows.entries()){
  if(!row||typeof row.id!=='string'||!Number.isSafeInteger(row.quantity)||row.quantity<1||row.quantity>99||typeof row.option!=='string'||row.option.length>300)throw new ShopError(400,'렌탈 상품과 수량을 확인해주세요.');
  const id=catalog.redirects[row.id]||row.id,p=products.get(id);
  if(!p||p.kind!=='rental'||p.status==='soldout')throw new ShopError(409,'렌탈 가능한 상품을 다시 선택해주세요.');
  const rates=detail(p).rental?.rates||[];
  if(row.option&&!rates.some(rate=>rate.label===row.option))throw new ShopError(409,'렌탈 요금 구성이 변경되었습니다. 다시 선택해주세요.');
  const identity=JSON.stringify([id,row.option]);if(seen.has(identity))throw new ShopError(400,'같은 렌탈 상품·구성은 수량으로 합쳐주세요.');seen.add(identity);
  let unit=null;
  if(prices!==null){const value=prices[index];if(!value||value.id!==id||value.option!==row.option||!Number.isSafeInteger(value.unit_price)||value.unit_price<1||value.unit_price>100000000)throw new ShopError(400,'전체 대여 기간의 확정 단가를 상품별로 입력해주세요.');unit=value.unit_price;}
  lines.push({id,name:p.name,option:row.option,quantity:row.quantity,unit_price:unit,image:p.image,shipping_class:'pickup',source_revision:catalog.meta.revision});
 }
 const subtotal=prices===null?null:lines.reduce((n,line)=>n+line.unit_price*line.quantity,0);
 if(subtotal!==null&&(!Number.isSafeInteger(subtotal)||subtotal<1||subtotal>100000000))throw new ShopError(400,'렌탈 금액이 온라인 처리 범위를 넘었습니다.');
 return {lines,subtotal,shipping:0,total:subtotal};
}
module.exports={rentalSchedule,rentalCustomer,rentalQuote};
