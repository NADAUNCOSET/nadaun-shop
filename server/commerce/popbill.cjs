'use strict';
// Optional electronic tax invoice provider. Enabling it requires the seller's
// own Popbill contract, certificate, funded points and verified tax profile.
// https://developers.popbill.com/reference/taxinvoice/node/api/issue
const {businessNumber}=require('./evidence.cjs');
function popbill(env,provided=null){
 if(env.SHOP_TAX_INVOICE_ENABLED!=='true')return null;
 const mode=env.SHOP_PAYMENT_MODE;
 if(env.SHOP_TAX_INVOICE_PROVIDER!=='popbill'||!['test','live'].includes(mode)||env.SHOP_POPBILL_MODE!==mode||
  !env.SHOP_POPBILL_LINK_ID||!env.SHOP_POPBILL_SECRET_KEY||!env.SHOP_POPBILL_USER_ID||
  !businessNumber(env.SHOP_SELLER_CORP_NUM)||!env.SHOP_SELLER_CORP_NAME||!env.SHOP_SELLER_CEO_NAME||
  env.SHOP_TAX_PROFILE!=='taxable_vat_included'||(mode==='live'&&env.SHOP_TAX_INVOICE_LIVE_VERIFIED!=='true'))throw Error('Tax invoice configuration incomplete');
 let service=provided;
 if(!service){
  // Construct a separate client so a cached SDK singleton cannot mix modes.
  const TaxinvoiceService=require('popbill/lib/TaxinvoiceService');
  service=new TaxinvoiceService({LinkID:env.SHOP_POPBILL_LINK_ID,SecretKey:env.SHOP_POPBILL_SECRET_KEY,IsTest:mode==='test',IPRestrictOnOff:true,UseStaticIP:false,UseLocalTimeYN:false});
 }
 function call(method,...args){return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(Error('Tax provider response pending')),18000);
  service[method](...args,value=>{clearTimeout(timer);resolve(value);},()=>{clearTimeout(timer);reject(Error('Tax provider request failed'));});
 });}
 function validate(value,key,order,buyer){
  if(value.invoicerMgtKey!==key||value.invoicerCorpNum!==env.SHOP_SELLER_CORP_NUM||value.invoiceeCorpNum!==buyer.corp_num||Number(value.totalAmount)!==order.total||value.taxType!=='과세')throw Error('Tax invoice identity mismatch');
 }
 return {mode,
  async lookup(key,order,buyer){
   const used=await call('checkMgtKeyInUse',env.SHOP_SELLER_CORP_NUM,'SELL',key);
   if(used===false)return null;
   if(used!==true)throw Error('Tax invoice lookup uncertain');
   const detail=await call('getDetailInfo',env.SHOP_SELLER_CORP_NUM,'SELL',key,env.SHOP_POPBILL_USER_ID);
   validate(detail,key,order,buyer);
   const info=await call('getInfo',env.SHOP_SELLER_CORP_NUM,'SELL',key,env.SHOP_POPBILL_USER_ID);
   if(![300,301,302,303,304].includes(info.stateCode)||!/^\d{24}$/.test(info.ntsconfirmNum||''))throw Error('Tax invoice not issued or needs review');
   return {issued:true,approval_number:info.ntsconfirmNum,issued_at:info.issueDT||null,nts_status:info.stateCode===304?'accepted':'pending'};
  },
  async issue(key,order,buyer,approvedAt){
   if(!Number.isSafeInteger(approvedAt))throw Error('Verified payment date required');
   const tax=Math.round(order.total/11),supply=order.total-tax;
   const lines=JSON.parse(order.lines_json),writeDate=new Date(approvedAt+9*3600000).toISOString().slice(0,10).replaceAll('-','');
   const invoice={writeDate,issueType:'정발행',taxType:'과세',chargeDirection:'정과금',purposeType:'영수',
    invoicerMgtKey:key,invoicerCorpNum:env.SHOP_SELLER_CORP_NUM,invoicerCorpName:env.SHOP_SELLER_CORP_NAME,invoicerCEOName:env.SHOP_SELLER_CEO_NAME,
    invoicerAddr:env.SHOP_SELLER_ADDRESS||'',invoicerBizType:env.SHOP_SELLER_BIZ_TYPE||'',invoicerBizClass:env.SHOP_SELLER_BIZ_CLASS||'',
    invoiceeType:'사업자',invoiceeCorpNum:buyer.corp_num,invoiceeCorpName:buyer.corp_name,invoiceeCEOName:buyer.ceo_name,
    invoiceeAddr:buyer.address,invoiceeBizType:buyer.biz_type,invoiceeBizClass:buyer.biz_class,invoiceeEmail1:buyer.email,
    supplyCostTotal:String(supply),taxTotal:String(tax),totalAmount:String(order.total),cash:String(order.total),remark1:order.id,
    detailList:[{serialNum:1,purchaseDT:writeDate,itemName:(lines[0].name+(lines.length>1?' 외 '+(lines.length-1)+'종':'')+' (배송비 포함)').slice(0,100),qty:'1',supplyCost:String(supply),tax:String(tax)}]};
   const result=await call('registIssue',env.SHOP_SELLER_CORP_NUM,invoice,false,false,'온라인 주문 '+order.id,'','',env.SHOP_POPBILL_USER_ID);
   if(result.code!==1||!/^\d{24}$/.test(result.ntsConfirmNum||''))throw Error('Tax invoice issue not confirmed');
   return {issued:true,approval_number:result.ntsConfirmNum,issued_at:writeDate,nts_status:'pending'};
  }
 };
}
module.exports={popbill};
