'use strict';
const {ShopError}=require('./security.cjs');
const lineKey=line=>JSON.stringify([line.id,line.option||'']);
const lineView=line=>({id:line.id,option:line.option||'',name:line.name,quantity:line.quantity});
function shipments(row,customer){
 if(customer.rental)return [];
 if(Array.isArray(customer._admin_shipments))return customer._admin_shipments;
 if(row.fulfillment==='shipped')return [{id:'legacy',purpose:'original',items:JSON.parse(row.lines_json).map(lineView),carrier:row.carrier||'',tracking:row.tracking||'',created_at:null,updated_at:null}];
 return [];
}
function publicShipments(rows){
 return rows.map(s=>({id:s.id,purpose:s.purpose,case_id:s.case_id||null,items:s.items.map(lineView),carrier:s.carrier,tracking:s.tracking,created_at:s.created_at,updated_at:s.updated_at}));
}
function remaining(allowed,used=[]){
 const counts=new Map();
 for(const item of used){const key=lineKey(item);if(!Number.isSafeInteger(item.quantity)||item.quantity<1)throw new ShopError(409,'저장된 품목 수량을 확인해주세요.');counts.set(key,(counts.get(key)||0)+item.quantity);}
 const keys=new Set(allowed.map(lineKey));
 if([...counts.keys()].some(key=>!keys.has(key)))throw new ShopError(409,'저장된 출고 품목과 주문을 확인해주세요.');
 return allowed.map(item=>{const quantity=item.quantity-(counts.get(lineKey(item))||0);if(!Number.isSafeInteger(quantity)||quantity<0)throw new ShopError(409,'이미 처리한 수량을 다시 확인해주세요.');return {...lineView(item),quantity};}).filter(item=>item.quantity>0);
}
function selectItems(input,allowed,{optional=false}={}){
 if(input===undefined&&optional)input=allowed.map(({id,option,quantity})=>({id,option,quantity}));
 if(!Array.isArray(input)||!input.length||input.length>30)throw new ShopError(400,'처리할 상품과 수량을 선택해주세요.');
 const source=new Map(allowed.map(item=>[lineKey(item),item])),seen=new Set();
 return input.map(item=>{
  if(!item||typeof item.id!=='string'||typeof item.option!=='string'||!Number.isSafeInteger(item.quantity)||item.quantity<1)throw new ShopError(400,'상품 구성과 수량을 확인해주세요.');
  const key=lineKey(item),original=source.get(key);
  if(seen.has(key))throw new ShopError(400,'같은 상품·구성은 수량으로 합쳐주세요.');seen.add(key);
  if(!original||item.quantity>original.quantity)throw new ShopError(409,'처리 가능한 잔여 수량을 초과했습니다. 최신 내역을 확인해주세요.');
  return {...lineView(original),quantity:item.quantity};
 });
}
function tracking(input){
 if(typeof input.carrier!=='string'||typeof input.tracking!=='string'||!/^[가-힣a-zA-Z0-9 .-]{2,40}$/.test(input.carrier)||!/^\d[\d-]{5,29}$/.test(input.tracking))throw new ShopError(400,'택배사와 운송장 번호를 확인해주세요.');
 return {carrier:input.carrier,tracking:input.tracking};
}
function originalRemaining(row,history){return remaining(JSON.parse(row.lines_json),history.filter(s=>s.purpose==='original').flatMap(s=>s.items));}
function caseRemaining(shipment,cases){return remaining(shipment.items,cases.filter(c=>c.shipment_id===shipment.id&&c.status!=='rejected').flatMap(c=>c.items));}
function replacementRemaining(item,history){return remaining(item.items,history.filter(s=>s.purpose==='exchange'&&s.case_id===item.id).flatMap(s=>s.items));}
function adminCases(cases,history){
 return cases.map(item=>{if(item.kind!=='exchange')return {...item};const replacement_remaining=replacementRemaining(item,history);return {...item,replacement_remaining,replacement_complete:replacement_remaining.length===0};});
}
module.exports={shipments,publicShipments,remaining,selectItems,tracking,originalRemaining,caseRemaining,replacementRemaining,adminCases};
