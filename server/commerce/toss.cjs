'use strict';
const {ShopError}=require('./security.cjs');
function toss(env,fetcher=fetch){
 const prefix=env.SHOP_PAYMENT_MODE==='live'?'live_':'test_';
 const client=env.SHOP_TOSS_CLIENT_KEY,secret=env.SHOP_TOSS_SECRET_KEY;
 if(!['test','live'].includes(env.SHOP_PAYMENT_MODE)||!client?.startsWith(prefix+'gck_')||!secret?.startsWith(prefix+'gsk_'))throw new ShopError(503,'주문서형 결제 서비스 연결을 준비 중입니다.');
 async function call(method,path,body,key){
  let res,value;
  try{res=await fetcher('https://api.tosspayments.com/v1/payments'+path,{method,headers:{Authorization:'Basic '+Buffer.from(secret+':').toString('base64'),'Content-Type':'application/json',...(key?{'Idempotency-Key':key}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(12000)});value=await res.json();}catch{throw new ShopError(503,'결제 결과를 확인 중입니다. 다시 결제하지 말고 주문 상태를 확인해주세요.');}
  if(!res.ok)throw new ShopError(502,'결제사 응답을 확인하지 못했습니다. 주문 상태를 다시 확인해주세요.');
  return value;
 }
 return {clientKey:client,mode:env.SHOP_PAYMENT_MODE,
  confirm:({paymentKey,orderId,amount},key)=>call('POST','/confirm',{paymentKey,orderId,amount},key),
  get:key=>call('GET','/'+encodeURIComponent(key))};
}
function matchPayment(value,order){
 if(value?.orderId!==order.id||value.paymentKey!==order.payment_key||value.totalAmount!==order.total||value.currency!=='KRW')throw new ShopError(502,'결제 금액 또는 주문 연결 확인이 필요합니다.');
 if(!['DONE','CANCELED','PARTIAL_CANCELED','IN_PROGRESS','WAITING_FOR_DEPOSIT','READY','ABORTED','EXPIRED'].includes(value.status))throw new ShopError(502,'결제 상태 확인이 필요합니다.');
 return value.status;
}
module.exports={toss,matchPayment};
