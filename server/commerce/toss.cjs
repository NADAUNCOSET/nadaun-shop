'use strict';
// Toss Payments SDK v2 / API individual integration. Secrets never reach the browser.
const crypto=require('node:crypto');
const {ShopError}=require('./security.cjs');
const ORIGIN='https://shop.nadaun.co',SDK='https://js.tosspayments.com/v2/standard';
const paymentKey=value=>typeof value==='string'&&/^[a-zA-Z0-9_-]{1,200}$/.test(value);
function receiptUrl(value){
 try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&!u.port&&['dashboard.tosspayments.com','pgweb.tosspayments.com','receipt.tosspayments.com'].includes(u.hostname)?u.href:null;}catch{return null;}
}
function matchPayment(value,order){
 if(value?.provider!=='toss'||value.orderId!==order.id||value.paymentKey!==order.payment_key||value.totalAmount!==order.total||value.currency!=='KRW'||!['DONE','CANCELED','PARTIAL_CANCELED'].includes(value.status))
  throw new ShopError(502,'결제 금액 또는 주문 연결 확인이 필요합니다.');
 return value.status;
}
function toss(env,fetcher=fetch){
 const mode=env.SHOP_PAYMENT_MODE,client=env.SHOP_TOSS_CLIENT_KEY,secret=env.SHOP_TOSS_SECRET_KEY,mid=env.SHOP_TOSS_MID;
 if(!['test','live'].includes(mode)||!new RegExp('^'+mode+'_ck_[a-zA-Z0-9_-]+$').test(client||'')||!new RegExp('^'+mode+'_sk_[a-zA-Z0-9_-]+$').test(secret||'')||
   (mode==='live'&&(!/^[a-zA-Z0-9_-]{1,50}$/.test(mid||'')||env.SHOP_TOSS_LIVE_VERIFIED!=='true')))
  throw new ShopError(503,'토스페이먼츠 결제 서비스 연결을 준비 중입니다.');
 async function call(method,path,body,key){
  let response,value;
  try{response=await fetcher('https://api.tosspayments.com/v1/payments'+path,{method,redirect:'error',headers:{Authorization:'Basic '+Buffer.from(secret+':').toString('base64'),'Content-Type':'application/json',...(key?{'Idempotency-Key':key}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(12000)});value=await response.json();}
  catch{throw new ShopError(503,'결제 결과를 확인 중입니다. 중복 결제하지 말고 주문 상태를 확인해주세요.');}
  if(!response.ok)throw new ShopError(502,'결제사 응답을 확인하지 못했습니다. 주문 상태를 확인해주세요.');
  return value;
 }
 function normalized(v){
  if(!v||!paymentKey(v.paymentKey)||typeof v.orderId!=='string'||!Number.isSafeInteger(v.totalAmount)||v.currency!=='KRW'||(mid&&v.mId!==mid))throw new ShopError(502,'토스페이먼츠 거래 연결을 확인해주세요.');
  const c=v.cashReceipt,approval=v.card?.approveNo;
  return {provider:'toss',orderId:v.orderId,paymentKey:v.paymentKey,totalAmount:v.totalAmount,currency:v.currency,status:v.status,
   balanceAmount:v.balanceAmount,isPartialCancelable:v.isPartialCancelable===true,useEscrow:v.useEscrow===true,
   cancels:Array.isArray(v.cancels)?v.cancels.map(c=>({transactionKey:c.transactionKey,cancelAmount:c.cancelAmount,cancelStatus:c.cancelStatus,canceledAt:c.canceledAt})):[],
   method:v.card?'CARD':['계좌이체','TRANSFER'].includes(v.method)?'BANK':'OTHER',
   approvedAt:v.approvedAt,approvalDate:typeof v.approvedAt==='string'?v.approvedAt.slice(0,10):null,
   approvalNumber:typeof approval==='string'&&/^\d{1,20}$/.test(approval)?approval:null,
   receiptUrl:receiptUrl(c?.receiptUrl||v.receipt?.url),
   cashReceipt:c?{present:true,issued:typeof c.issueNumber==='string'&&/^\d{1,20}$/.test(c.issueNumber),amount:c.amount,purpose:{'소득공제':'income','지출증빙':'business'}[c.type]||null,approvalNumber:c.issueNumber,issuedAt:v.approvedAt||null}:{present:false,issued:false}};
 }
 const stable=(kind,id)=>'nadaun-'+kind+'-'+crypto.createHash('sha256').update(id).digest('hex').slice(0,40);
 async function get(key){if(!paymentKey(key))throw new ShopError(400,'결제 거래번호를 확인해주세요.');return normalized(await call('GET','/'+encodeURIComponent(key)));}
 return {provider:'toss',mode,clientKey:client,
  prepare(order,customer,token){
   if(!Number.isSafeInteger(order.total)||order.total<1||order.total>100000000)throw new ShopError(400,'확정 결제 금액을 확인해주세요.');
   const kind=customer.evidence?.kind||'card_receipt';if(!['card_receipt','cash_receipt','tax_invoice'].includes(kind))throw new ShopError(400,'증빙 종류를 확인해주세요.');
   const lines=JSON.parse(order.lines_json),request={method:kind==='card_receipt'?'CARD':'TRANSFER',amount:{currency:'KRW',value:order.total},orderId:order.id,orderName:(lines[0].name+(lines.length>1?' 외 '+(lines.length-1)+'건':'')).slice(0,100),successUrl:ORIGIN+'/api/toss-return?token='+encodeURIComponent(token),failUrl:ORIGIN+'/orders.html?result=closed',customerName:customer.name,customerMobilePhone:customer.phone.replace(/[^0-9]/g,'')};
   if(kind==='card_receipt')request.card={flowMode:'DEFAULT'};
   else request.transfer={cashReceipt:{type:kind==='tax_invoice'?'미발행':'소득공제'}};
   return {provider:'toss',mode,clientKey:client,orderId:order.id,amount:order.total,request};
  },
  validateAuthentication(input,order){
   if(input.orderId!==order.id||!paymentKey(input.paymentKey)||typeof input.amount!=='string'||!/^\d{1,9}$/.test(input.amount)||Number(input.amount)!==order.total)throw new ShopError(400,'결제 인증 금액과 주문 정보를 확인해주세요.');
   return {paymentKey:input.paymentKey,orderId:order.id,amount:order.total};
  },
  async approve(auth,order){
   const v=normalized(await call('POST','/confirm',auth,stable('confirm',order.id)));
   matchPayment(v,{...order,payment_key:auth.paymentKey});
   if(v.status!=='DONE')throw new ShopError(502,'결제 승인이 완료되지 않았습니다.');
   return v;
  },
  async netCancel(auth,order,reason='주문 승인 저장 실패로 자동 취소'){
   // Resolve by authenticated GET before compensation; never cancel a foreign transaction.
   let remote=await get(auth.paymentKey);matchPayment(remote,{...order,payment_key:auth.paymentKey});
   if(remote.status==='CANCELED')return {canceled:true,paymentKey:auth.paymentKey};
   if(remote.status!=='DONE')throw new ShopError(503,'결제 취소 결과를 확인해주세요.');
   remote=normalized(await call('POST','/'+encodeURIComponent(auth.paymentKey)+'/cancel',{cancelReason:reason},stable('compensate',order.id)));
   matchPayment(remote,{...order,payment_key:auth.paymentKey});
   if(remote.status!=='CANCELED')throw new ShopError(503,'결제 취소 결과를 확인해주세요.');
   return {canceled:true,paymentKey:auth.paymentKey};
  },
  async cancel(order,operation){
   const remote=await get(order.payment_key);matchPayment(remote,order);
   if(!Number.isSafeInteger(operation.amount)||operation.amount<1||!Number.isSafeInteger(operation.before_balance)||operation.amount>operation.before_balance||typeof operation.reason!=='string'||operation.reason.length<2||operation.reason.length>200||!/^RF-[a-zA-Z0-9-]{20,60}$/.test(operation.id))throw new ShopError(400,'취소 금액과 사유를 확인해주세요.');
   // refundableAmount is an additional provider-side concurrent balance check.
   // Replays MUST use the same key and body, including after an ambiguous timeout.
   const result=normalized(await call('POST','/'+encodeURIComponent(order.payment_key)+'/cancel',{cancelReason:operation.reason,cancelAmount:operation.amount,refundableAmount:operation.before_balance},stable('refund',operation.id)));
   matchPayment(result,order);return result;
  },get
 };
}
module.exports={toss,matchPayment,receiptUrl,SDK,ORIGIN};
