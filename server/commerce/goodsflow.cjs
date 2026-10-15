'use strict';
const {ShopError}=require('./security.cjs');
const CARRIERS={LOGEN:'로젠택배',KOREX:'CJ대한통운',HANJIN:'한진택배',LOTTE:'롯데택배',EPOST:'우체국소포',ILYANG:'일양로지스'};
const BOXES=new Set(['B01','B02','B05','B10','B20','B25','B30']);
const clean=(value,max,label,optional=false)=>{
 const text=String(value??'').trim();
 if((!optional&&!text)||text.length>max||/[\x00-\x1f\x7f]/.test(text))throw new ShopError(400,label+'을 확인해주세요.');
 return text;
};
function goodsflow(env=process.env,fetcher=fetch,clock=()=>Date.now()){
 const mode=env.SHOP_GOODSFLOW_MODE==='live'?'live':'test',key=env.SHOP_GOODSFLOW_API_KEY||'';
 const enabled=env.SHOP_GOODSFLOW_ENABLED==='true'&&mode==='live'&&!!key;
 const base=mode==='live'?'https://api.goodsflow.io':'https://test-api.goodsflow.io';
 async function request(method,path,body){
  if(!key)throw new ShopError(503,'우리몰 굿스플로 API 연결을 준비 중입니다.');
  let response,value;
  try{
   response=await fetcher(base+path,{method,redirect:'error',headers:{Authorization:key,'Content-Type':'application/json'},...(body!==undefined?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(12000)});
   value=await response.json();
  }catch{throw new ShopError(503,'굿스플로 응답을 확인하지 못했습니다. 접수 요청을 반복하지 말고 결과를 조회해주세요.');}
  // Never relay upstream messages: they can include addresses, tokens or raw payloads.
  if(!response.ok||value?.success!==true)throw new ShopError(503,'굿스플로 연결 또는 처리 결과를 확인해주세요.');
  return value.data;
 }
 async function contracts(){
  const data=await request('GET','/api/contracts'),today=new Date(clock()+9*3600000).toISOString().slice(0,10);
  if(!Array.isArray(data))throw new ShopError(503,'굿스플로 계약 정보를 확인해주세요.');
  return data.filter(c=>c.status==='APPROVED'&&CARRIERS[c.transporter]&&c.center?.enabled===true&&c.startDate<=today&&c.endDate>=today)
   .map(c=>({...c,boxes:(c.contractRates||[]).filter(r=>BOXES.has(r.boxSize)&&Number.isSafeInteger(c.deliveryCalcStandard==='CREDIT_CALC'?r.creditCost:r.prepaidCost)&&(c.deliveryCalcStandard==='CREDIT_CALC'?r.creditCost:r.prepaidCost)>0)})).filter(c=>c.boxes.length);
 }
 async function contract(id,box){
  const result=(await contracts()).find(c=>c.contractId===id&&c.boxes.some(b=>b.boxSize===box));
  if(!result)throw new ShopError(409,'승인된 계약의 유효기간과 박스 규격을 다시 확인해주세요.');
  return result;
 }
 function payload(order,customer,selected,box,uniqueId){
  const from=selected.center;
  const phone=value=>clean(String(value||'').replace(/[ -]/g,''),12,'연락처');
  const item={centerCode:clean(from.code,10,'출고지 코드'),uniqueId,boxSize:box,transporter:selected.transporter,
   fromName:clean(from.name,50,'출고지 이름'),fromPhoneNo:phone(from.phoneNo1),fromZipcode:clean(from.zipCode,6,'출고지 우편번호'),fromAddress1:clean(from.address1,100,'출고지 주소'),fromAddress2:clean(from.address2,100,'출고지 상세주소',true),
   toName:clean(customer.name,50,'수령인'),toPhoneNo:phone(customer.phone),toZipcode:clean(customer.postcode,6,'우편번호'),toAddress1:clean(customer.address,100,'배송지 주소'),toAddress2:clean(customer.address_detail,100,'상세주소',true),deliveryPaymentMethod:'SENDER_PAY',
   deliveryItems:JSON.parse(order.lines_json).map(line=>{
    if(!Number.isSafeInteger(line.unit_price)||line.unit_price<1||!Number.isSafeInteger(line.quantity)||line.quantity<1)throw new ShopError(409,'확정된 상품 단가와 수량이 필요합니다.');
    return {orderNo:order.id,orderDate:new Date(order.created_at+9*3600000).toISOString().slice(0,16).replace('T',' '),name:clean(line.name,250,'상품명'),option:clean(line.option,255,'상품 구성',true),quantity:line.quantity,price:line.unit_price,defCode1:'',defCode2:''};
   })};
  if(!/^\d{5,6}$/.test(item.toZipcode)||!/^\d{5,6}$/.test(item.fromZipcode)||![item.toPhoneNo,item.fromPhoneNo].every(n=>/^\d{8,12}$/.test(n)))throw new ShopError(400,'출고지와 배송지의 우편번호·연락처를 확인해주세요.');
  return {contractType:'USER',items:[item]};
 }
 return {
  enabled,mode,configured:!!key,carrierNames:CARRIERS,contracts,contract,payload,
  async register(body){
   const data=await request('POST','/api/deliveries/shipping/print/deliveryItems',body),item=data?.items?.[0];
   if(data?.totalCnt!==1||data?.successCnt!==1||data?.items?.length!==1||item?.success!==true||item.data?.uniqueId!==body.items[0].uniqueId||!/^\d{1,40}$/.test(item.data?.serviceId||''))throw new ShopError(503,'송장 접수 결과를 조회해주세요. 재접수는 보류합니다.');
   return item.data;
  },
  async lookup(uniqueId){
   const rows=await request('GET','/api/deliveries/'+encodeURIComponent(uniqueId)+'?idType=uniqueId');
   if(!Array.isArray(rows)||rows.length>1||rows.some(r=>r.uniqueId!==uniqueId))throw new ShopError(503,'송장 조회 결과가 일치하지 않습니다.');
   return rows[0]||null;
  },
  async print(ids,includePrinted=false){
   const data=await request('PUT','/api/deliveries/shipping/print-uri?idType=serviceId&includePrinted='+String(includePrinted),ids);
   let url;try{url=new URL(data?.uri);}catch{throw new ShopError(503,'송장 출력 주소를 확인해주세요.');}
   const host=mode==='live'?'admin.goodsflow.io':'test-api-doc.goodsflow.io';
   if(url.protocol!=='https:'||url.hostname!==host||url.port||url.username||url.password||!url.pathname.startsWith('/invoice-print/public/print/')||data.requestCount!==ids.length||data.printCount!==ids.length)throw new ShopError(503,'선택한 송장의 출력 가능 여부를 확인해주세요.');
   return {uri:url.href,count:data.printCount,expires_at:data.expireDateTime};
  }
 };
}
module.exports={goodsflow,CARRIERS};
