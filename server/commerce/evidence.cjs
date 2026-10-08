'use strict';
const {ShopError}=require('./security.cjs');
const kinds=new Set(['card_receipt','cash_receipt','tax_invoice']);
function businessNumber(value){
 if(!/^\d{10}$/.test(value||'')||/^0+$/.test(value))return false;
 const n=[...value].map(Number),w=[1,3,7,1,3,7,1,3,5];
 const sum=w.reduce((s,v,i)=>s+v*n[i],0)+Math.floor(n[8]*5/10);
 return (10-sum%10)%10===n[9];
}
function evidenceFields(raw={kind:'card_receipt'}){
 if(!raw||typeof raw!=='object'||Array.isArray(raw)||!kinds.has(raw.kind))throw new ShopError(400,'결제 증빙 종류를 선택해주세요.');
 const result={kind:raw.kind};
 if(raw.kind!=='tax_invoice')return result;
 for(const [key,min,max] of [['corp_num',10,10],['corp_name',1,200],['ceo_name',1,100],['address',5,300],['biz_type',1,100],['biz_class',1,100],['email',5,100]]){
  const value=typeof raw[key]==='string'?raw[key].trim():'';
  if(value.length<min||value.length>max||/[\x00-\x1f\x7f<>]/.test(value))throw new ShopError(400,'세금계산서 사업자 정보를 확인해주세요.');
  result[key]=value;
 }
 if(!businessNumber(result.corp_num)||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(result.email))throw new ShopError(400,'사업자등록번호와 증빙 수신 이메일을 확인해주세요.');
 return result;
}
function paymentEvidence(remote,selection,total){
 const kind=selection?.kind||'card_receipt';
 const method=remote.method;
 // Evidence errors must never be mistaken for a failed payment approval.
 if(!kinds.has(kind)||!['CARD','BANK'].includes(method)||((kind==='card_receipt')!==(method==='CARD')))
  return {kind,status:'review',reason:'payment_method_mismatch'};
 if(kind==='tax_invoice')return {kind,status:remote.cashReceipt?.issued?'review':'queued',reason:remote.cashReceipt?.issued?'existing_cash_receipt':null};
 if(kind==='card_receipt')return {kind,status:'issued',approval_number:remote.approvalNumber||null};
 const c=remote.cashReceipt;
 if(c?.issued&&c.amount===total&&['income','business'].includes(c.purpose)&&/^\d{1,20}$/.test(c.approvalNumber||''))
  return {kind,status:'issued',purpose:c.purpose,approval_number:c.approvalNumber,issued_at:c.issuedAt||null};
 return {kind,status:'retry',reason:c?.issued?'receipt_amount_mismatch':'receipt_unconfirmed'};
}
module.exports={evidenceFields,businessNumber,paymentEvidence};
