'use strict';
// KG INICIS INIpay PRO: https://manual.inicis.com/pay/pro.html
// Transaction inquiry: https://manual.inicis.com/pay/etc-inquiry.html (JSON v2).
const crypto=require('node:crypto');
const {ShopError}=require('./security.cjs');
const ORIGIN='https://shop.nadaun.co';
const SDK='https://paypro.inicis.com/std/payment/js/INIPayPro_v2.js';
const digest=(value,encoding='hex')=>crypto.createHash('sha512').update(value,'utf8').digest(encoding);
const tid=value=>typeof value==='string'&&/^[a-zA-Z0-9_-]{10,40}$/.test(value);
const amount=value=>typeof value==='string'&&/^[1-9]\d{0,8}$/.test(value)?Number(value):null;
function utf8(value,bytes){let out='';for(const char of String(value)){if(Buffer.byteLength(out+char,'utf8')>bytes)break;out+=char;}return out;}
function cashReceipt(v){return {issued:v.P_CSHR_CODE==='0000'&&!!v.P_CSHR_AUTH_NO,amount:amount(v.P_CSHR_AMT),purpose:v.P_CSHR_TYPE==='0'?'income':v.P_CSHR_TYPE==='1'?'business':null,approvalNumber:v.P_CSHR_AUTH_NO||null,issuedAt:/^\d{14}$/.test(v.P_CSHR_DT||'')?v.P_CSHR_DT:null};}
function queryReceipt(v){if(!v)return {issued:false};return {issued:v.issueStatus==='APPROVAL'&&v.approvedResultCode==='COMPLETED',present:v.issueStatus==='APPROVAL',approvalNumber:v.approvedNumber||null,issuedAt:/^\d{8}$/.test(v.approvedDate||'')?v.approvedDate+(v.approvedTime||''):null};}
function inicis(env,fetcher=fetch,clock=()=>Date.now()){
 const mode=env.SHOP_PAYMENT_MODE,mid=env.SHOP_INICIS_MID,key=env.SHOP_INICIS_HASH_KEY;
 if(!['test','live'].includes(mode)||!/^\w{10}$/.test(mid||'')||typeof key!=='string'||key.length<10||key.length>256||/\s/.test(key)||
    (mode==='test'&&mid!=='INIpayTest')||
    (mode==='live'&&(/test/i.test(mid)||env.SHOP_INICIS_LIVE_VERIFIED!=='true')))
  throw new ShopError(503,'이니시스 결제 서비스 연결을 준비 중입니다.');
 function host(idc){if(!['fc','ks','stg'].includes(idc)||(mode==='live'&&idc==='stg'))throw new ShopError(400,'결제사 인증 경로를 확인하지 못했습니다.');return `https://${idc}paypro.inicis.com`;}
 function signed(order){const timestamp=String(clock());return {P_TIMESTAMP:timestamp,P_CHKFAKE:digest(String(order.total)+order.id+timestamp+key,'base64')};}
 async function call(url,body,json=false){
  try{
   const res=await fetcher(url,{method:'POST',redirect:'error',headers:{'Content-Type':json?'application/json':'application/x-www-form-urlencoded;charset=UTF-8'},body:json?JSON.stringify(body):new URLSearchParams(body).toString(),signal:AbortSignal.timeout(15000)});
   if(!res.ok)throw Error('upstream');
   const raw=await res.text();if(raw.length>65536)throw Error('response size');
   const value=raw.trim().startsWith('{')?JSON.parse(raw):Object.fromEntries(new URLSearchParams(raw));
   if(!value||typeof value!=='object'||Array.isArray(value))throw Error('response format');return value;
  }catch{throw new ShopError(503,'결제 결과 확인이 필요합니다. 중복 결제하지 말고 주문 상태를 확인해주세요.');}
 }
 function validateAuthentication(input,order){
  if(input.P_STATUS!=='00'||input.P_MID!==mid||input.P_OID!==order.id||amount(input.P_AMT)!==order.total||!tid(input.P_AUTH_TID))
   throw new ShopError(409,'결제 인증 정보와 주문이 일치하지 않습니다.');
  host(input.P_IDCNAME);
  return {P_AUTH_TID:input.P_AUTH_TID,P_IDCNAME:input.P_IDCNAME};
 }
 return {provider:'inicis',mode,mid,
  prepare(order,customer,token,device='WEB'){
   if(!['WEB','MOBILE'].includes(device)||!Number.isSafeInteger(order.total)||order.total<=0||order.total>100000000||!/^[a-zA-Z0-9_-]{1,40}$/.test(order.id))throw new ShopError(400,'결제 요청 정보를 확인해주세요.');
   const kind=customer.evidence?.kind||'card_receipt';
   if(!['card_receipt','cash_receipt','tax_invoice'].includes(kind))throw new ShopError(400,'결제 증빙 종류를 확인해주세요.');
   return {provider:'inicis',mode,orderId:order.id,amount:order.total,sdkUrl:SDK,fields:{
    P_MID:mid,P_OID:order.id,P_PAY_TYPE:kind==='card_receipt'?'CARD':'BANK',P_DEVICE_TYPE:device,P_IDCCODE:'Y',P_AMT:String(order.total),
    P_GOODS:utf8(JSON.parse(order.lines_json)[0].name+(JSON.parse(order.lines_json).length>1?' 외':''),80),P_UNAME:utf8(customer.name,30),
    P_NEXT_URL:ORIGIN+'/api/inicis-return',P_CLOSE_URL:ORIGIN+'/api/inicis-return?action=close',P_CHARSET:'UTF-8',P_LANG:'ko',
    P_RESERVED:JSON.stringify({phonenum:customer.phone.replace(/[^0-9]/g,''),...(kind==='tax_invoice'?{bank_receipt:'N'}:{})}),P_NOTI:token,...signed(order)}};
  },
  validateAuthentication,
  async approve(auth,order){
   const v=await call(host(auth.P_IDCNAME)+'/payment/v1/rest/payAppl.ini',{P_MID:mid,P_AUTH_TID:auth.P_AUTH_TID,P_AMT:String(order.total),P_CHARSET:'UTF-8'});
   if(v.P_STATUS!=='00'||v.P_MID!==mid||v.P_OID!==order.id||amount(v.P_AMT)!==order.total||v.P_AUTH_TID!==auth.P_AUTH_TID||!tid(v.P_APPL_TID)||!['CARD','BANK'].includes(v.P_TYPE))
    throw new ShopError(502,'이니시스 승인 결과와 주문 정보가 일치하지 않습니다.');
   const day=v.P_APPL_DT||'',date=/^20\d{6}$/.test(day)?day.slice(0,4)+'-'+day.slice(4,6)+'-'+day.slice(6):null;
   const validDate=date&&Number.isFinite(Date.parse(date+'T00:00:00Z'))&&new Date(date+'T00:00:00Z').toISOString().slice(0,10)===date;
   return {orderId:v.P_OID,paymentKey:v.P_APPL_TID,totalAmount:amount(v.P_AMT),currency:'KRW',status:'DONE',provider:'inicis',method:v.P_TYPE,approvalDate:validDate?date:null,approvalNumber:/^\d{1,20}$/.test(v.P_APPL_NO||'')?v.P_APPL_NO:null,cashReceipt:cashReceipt(v)};
  },
  async netCancel(auth,order){
   const v=await call(host(auth.P_IDCNAME)+'/payment/v1/rest/payNetCancel.ini',{P_MID:mid,P_AUTH_TID:auth.P_AUTH_TID,P_AMT:String(order.total),P_OID:order.id,P_CANCEL_MSG:'Order confirmation could not be persisted',P_CHARSET:'UTF-8',...signed(order)});
   if(v.P_STATUS!=='00')throw new ShopError(503,'결제 취소 결과를 확인해야 합니다. 고객센터에 주문번호를 알려주세요.');
   return {canceled:true,paymentKey:tid(v.P_APPL_TID)?v.P_APPL_TID:null};
  },
  async get(paymentKey){
   if(!tid(paymentKey)||typeof env.SHOP_INICIS_API_KEY!=='string'||env.SHOP_INICIS_API_KEY.length<16||require('node:net').isIP(env.SHOP_INICIS_CLIENT_IP||'')!==4)
    throw new ShopError(503,'이니시스 거래조회 설정을 확인해주세요.');
   const timestamp=new Date(clock()+9*3600*1000).toISOString().replace(/\D/g,'').slice(0,14),data={tid:paymentKey};
   const request={mid,type:'inquiry',timestamp,clientIp:env.SHOP_INICIS_CLIENT_IP,data,hashData:digest(env.SHOP_INICIS_API_KEY+mid+'inquiry'+timestamp+JSON.stringify(data))};
   const v=await call('https://iniapi.inicis.com/v2/pg/inquiry',request,true);
   const states={APPROVAL:'DONE',CANCEL:'CANCELED',PART_CANCEL:'PARTIAL_CANCELED'};
   if(v.resultCode!=='SUCCESS'||v.mid!==mid||v.tid!==paymentKey||!states[v.transactionStatus]||!['Card','VCard','DirectBank'].includes(v.paymethod)||
     (v.cardInfo?.currencyCode&&!['KRW','WON','410'].includes(v.cardInfo.currencyCode)))throw new ShopError(502,'이니시스 거래 상태 확인이 필요합니다.');
   return {provider:'inicis',orderId:v.oid,paymentKey:v.tid,totalAmount:amount(v.price),currency:'KRW',status:states[v.transactionStatus],method:['Card','VCard'].includes(v.paymethod)?'CARD':'BANK',approvalNumber:/^\d{1,20}$/.test(v.cardInfo?.approvedNumber||'')?v.cardInfo.approvedNumber:null,cashReceipt:queryReceipt(v.cashReceiptInfo)};
  }
 };
}
function matchPayment(value,order){
 if(value?.provider!=='inicis'||value.orderId!==order.id||value.paymentKey!==order.payment_key||value.totalAmount!==order.total||value.currency!=='KRW'||!['DONE','CANCELED','PARTIAL_CANCELED'].includes(value.status))
  throw new ShopError(502,'결제 금액 또는 주문 연결 확인이 필요합니다.');
 return value.status;
}
module.exports={inicis,matchPayment,SDK,ORIGIN};
