'use strict';
const crypto=require('node:crypto');
const {ShopError}=require('./security.cjs');
const {matchPayment}=require('./toss.cjs');
const fulfillment=require('./fulfillment.cjs');
const activeRefund=c=>(c._admin_refunds||[]).find(r=>r.status==='pending');
const openRequest=c=>c._admin_cancel_request?.status==='requested';
const blocked=c=>!!activeRefund(c)||openRequest(c);
function amounts(payment,row,strict=false){
 matchPayment(payment,row);
 const balance=payment.balanceAmount??(payment.status==='DONE'?row.total:null);
 const cancellations=payment.cancels||[];
 const valid=Number.isSafeInteger(balance)&&balance>=0&&balance<=row.total&&
  (payment.status==='DONE'?balance===row.total:payment.status==='CANCELED'?balance===0:balance>0&&balance<row.total)&&
  (payment.status==='DONE'||cancellations.length>0)&&cancellations.every(c=>typeof c.transactionKey==='string'&&c.transactionKey.length>0&&c.transactionKey.length<=64&&c.cancelStatus==='DONE'&&Number.isSafeInteger(c.cancelAmount)&&c.cancelAmount>0&&Number.isFinite(Date.parse(c.canceledAt)))&&
  new Set(cancellations.map(c=>c.transactionKey)).size===cancellations.length&&cancellations.reduce((n,c)=>n+c.cancelAmount,0)===row.total-balance;
 if(!valid&&strict)throw new ShopError(502,'취소 거래 내역과 잔액을 확인해야 합니다. 새 환불을 실행하지 마세요.');
 return valid?{approved_amount:row.total,canceled_amount:row.total-balance,balance_amount:balance}:null;
}
function view(row,customer,cipher,admin=false){
 const payment=row.payment_receipt_cipher?cipher.decrypt(row.payment_receipt_cipher):null;
 let sums=null;try{if(payment)sums=amounts(payment,row);}catch{}
 const request=customer._admin_cancel_request,confirmed=customer._admin_purchase_confirmation;
 return {payment_summary:payment?{status:payment.status,...sums,partial_cancelable:payment.isPartialCancelable===true,escrow:payment.useEscrow===true,checked_at:customer._admin_payment_checked_at||row.paid_at||null,cancellations:sums?(payment.cancels||[]).map(c=>({amount:c.cancelAmount,canceled_at:c.canceledAt,status:c.cancelStatus})):[]}:null,
  cancellation_request:request?{id:request.id,status:request.status,reason:request.reason,created_at:request.created_at,response:request.response||null}:null,
  purchase_confirmation:confirmed?{confirmed_at:confirmed.confirmed_at,source:'customer'}:null,
  refund_pending:!!activeRefund(customer),...(admin?{admin_refunds:customer._admin_refunds||[]}:{}),
  can_confirm_purchase:row.state==='PAID'&&row.fulfillment==='shipped'&&!customer.rental&&!confirmed&&!blocked(customer)&&!payment?.useEscrow&&!(customer._admin_cases||[]).some(c=>!['closed','rejected'].includes(c.status))&&fulfillment.shipments(row,customer).filter(s=>s.purpose==='original').length>0&&fulfillment.shipments(row,customer).filter(s=>s.purpose==='original').every(s=>s.delivered_at)};
}
function lifecycle({repo,cipher,payment,clock,own,editable,detailed,applyPayment,testing}){
 const text=value=>{if(typeof value!=='string'||value.trim().length<2||value.length>200||/[\x00-\x1f\x7f]/.test(value))throw new ShopError(400,'사유를 2~200자로 입력해주세요.');return value.trim();};
 function connected(row){if(!payment||row.payment_mode!==payment.mode||row.payment_provider!=='toss'||!row.payment_key)throw new ShopError(409,'이 주문의 토스 결제 연결 상태를 확인해주세요.');}
 // Merge against the newest row after network I/O; unrelated notes are preserved.
 async function saveResult(id,operationId,remote,actor){
  for(let attempt=0;attempt<3;attempt++){
   const row=await repo.get(id),customer=cipher.decrypt(row.customer_cipher),op=(customer._admin_refunds||[]).find(r=>r.id===operationId);
   if(!op)throw new ShopError(409,'환불 요청 기록을 확인해주세요.');
   if(op.status==='done')return detailed(row,true);
   const sums=amounts(remote,row,true),newCancels=(remote.cancels||[]).filter(c=>!op.before_transactions.includes(c.transactionKey));
   if(sums.balance_amount!==op.before_balance-op.amount||newCancels.reduce((n,c)=>n+c.cancelAmount,0)!==op.amount)throw new ShopError(409,'취소 결과가 요청 금액과 다릅니다. 결제사 거래를 대조해주세요.');
   op.status='done';op.completed_at=clock();op.transactions=newCancels.map(c=>c.transactionKey);
   if(openRequest(customer)){customer._admin_cancel_request.status='completed';customer._admin_cancel_request.response=op.amount===op.before_balance?'전액 취소 처리 확인':'부분 취소 처리 확인';}
   customer._admin_payment_checked_at=clock();
   try{return detailed(await repo.patch(row,{state:remote.status==='CANCELED'?'CANCELED':'PAYMENT_REVIEW',payment_receipt_cipher:cipher.encrypt(remote),customer_cipher:cipher.encrypt(customer)},actor,remote.status==='CANCELED'?'refund_completed':'refund_partial_completed'),true);}catch(e){if(e.status!==409||attempt===2)throw e;}
  }
 }
 return {
  async refund(id,input,actor){
   let row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');connected(row);
   const reason=text(input.reason),amount=input.amount,key=input.request_key;
   if(input.confirmed!==true||!Number.isSafeInteger(amount)||amount<1||amount>100000000||typeof key!=='string'||!/^[a-zA-Z0-9_-]{16,100}$/.test(key))throw new ShopError(400,'취소 금액·사유와 최종 확인을 입력해주세요.');
   let customer=cipher.decrypt(row.customer_cipher),op=(customer._admin_refunds||[]).find(r=>r.request_key===key);
   if(op&&(op.amount!==amount||op.reason!==reason))throw new ShopError(409,'같은 환불 요청의 내용이 변경되었습니다.');
   if(op?.status==='done')return detailed(row,true);
   if(!op){
    row=await editable(id,input);
    if(!['PAID','PAYMENT_REVIEW'].includes(row.state)||activeRefund(customer))throw new ShopError(409,'진행 중인 환불 결과를 먼저 확인해주세요.');
    if((customer._admin_refunds||[]).length>=100)throw new ShopError(409,'환불 기록을 확인해주세요.');
    const remote=await payment.get(row.payment_key),sums=amounts(remote,row,true);
    if(remote.useEscrow)throw new ShopError(409,'에스크로 거래는 토스 구매확정·취소 요청 상태를 먼저 확인해주세요.');
    if(amount>sums.balance_amount||amount<sums.balance_amount&&remote.isPartialCancelable!==true)throw new ShopError(409,'남은 결제 금액과 부분 취소 가능 여부를 확인해주세요.');
    op={id:'RF-'+crypto.randomUUID(),request_key:key,amount,reason,before_balance:sums.balance_amount,before_transactions:(remote.cancels||[]).map(c=>c.transactionKey),created_at:clock(),actor,status:'pending'};
    customer._admin_refunds=[...(customer._admin_refunds||[]),op];
    row=await repo.patch(row,{state:'PAYMENT_REVIEW',customer_cipher:cipher.encrypt(customer),payment_receipt_cipher:cipher.encrypt(remote)},actor,'refund_requested');
   }
   // Toss keys expire after 15 days. A stale retry may only be investigated;
   // it must never turn into a second financial request with an expired key.
   if(clock()-op.created_at>=14*86400000)throw new ShopError(409,'장기 미확정 환불입니다. 토스 거래를 대조해야 하며 자동 재실행은 중단했습니다.');
   try{return await saveResult(id,op.id,await payment.cancel(row,op),actor);}
   catch(error){if(error instanceof ShopError)throw error;throw new ShopError(503,'환불 결과 확인 중입니다. 같은 요청의 결과 재확인을 이용해주세요.');}
  },
  async customerCancel(id,owner,input){
   let row=await own(id,owner),customer=cipher.decrypt(row.customer_cipher);
   const reason=text(input.reason);
   if(openRequest(customer))return detailed(row);
   row=await editable(id,input);
   if(['REQUESTED','APPROVED'].includes(row.state)&&!row.payment_mode&&!row.payment_key){
    customer._admin_cancellation={reason,created_at:clock(),actor:'customer'};
    return detailed(await repo.patch(row,{state:'CANCELED',quote_expires:null,customer_cipher:cipher.encrypt(customer)},'customer','request_canceled'));
   }
   connected(row);
   if(!['PAID','PAYMENT_REVIEW'].includes(row.state)||activeRefund(customer))throw new ShopError(409,'현재 결제·환불 상태를 먼저 확인해주세요.');
   customer._admin_cancel_request={id:'CR-'+crypto.randomUUID(),status:'requested',reason,created_at:clock()};
   return detailed(await repo.patch(row,{state:'PAYMENT_REVIEW',customer_cipher:cipher.encrypt(customer)},'customer','customer_cancel_requested'));
  },
  async rejectCancellation(id,input,actor){
   const row=await editable(id,input),customer=cipher.decrypt(row.customer_cipher);connected(row);
   if(!openRequest(customer)||activeRefund(customer))throw new ShopError(409,'고객 요청과 진행 중인 환불을 확인해주세요.');
   const response=text(input.reason),remote=await payment.get(row.payment_key);amounts(remote,row,true);
   customer._admin_cancel_request.status=remote.status==='CANCELED'?'completed':'rejected';customer._admin_cancel_request.response=response;
   return detailed(await repo.patch(row,{state:remote.status==='DONE'?'PAID':remote.status==='CANCELED'?'CANCELED':'PAYMENT_REVIEW',customer_cipher:cipher.encrypt(customer),payment_receipt_cipher:cipher.encrypt(remote)},actor,'customer_cancel_resolved'),true);
  },
  async confirmPurchase(id,owner,input={}){
   let row=await own(id,owner),customer=cipher.decrypt(row.customer_cipher);connected(row);
   if(customer._admin_purchase_confirmation){row=await applyPayment(row,await payment.get(row.payment_key),'customer');if(row.state!=='PAID')throw new ShopError(409,'구매확정 이후 결제 상태가 변경되었습니다.');return detailed(row);}
   if(input.confirmed!==true||row.payment_mode!==(testing?'test':'live')||!view(row,customer,cipher).can_confirm_purchase)throw new ShopError(409,'전체 상품의 배송 완료와 취소·반품 상태를 확인해주세요.');
   row=await applyPayment(row,await payment.get(row.payment_key),'customer');customer=cipher.decrypt(row.customer_cipher);
   if(!view(row,customer,cipher).can_confirm_purchase)throw new ShopError(409,'결제·반품 상태가 변경되었습니다. 다시 확인해주세요.');
   customer._admin_purchase_confirmation={confirmed_at:clock(),source:'customer'};
   return detailed(await repo.patch(row,{customer_cipher:cipher.encrypt(customer)},'customer','purchase_confirmed'));
  },
  async paymentWebhook(input){
   if(!payment)return {accepted:false,reason:'disabled'};
   if(input?.eventType!=='PAYMENT_STATUS_CHANGED')return {accepted:true,ignored:true};
   const data=input.data;
   if(!data||typeof data.orderId!=='string'||!/^NS-[a-zA-Z0-9_-]{1,40}$/.test(data.orderId)||typeof data.paymentKey!=='string')throw new ShopError(400,'잘못된 결제 알림입니다.');
   const row=await repo.get(data.orderId);
   if(!row||row.payment_key!==data.paymentKey||row.payment_mode!==payment.mode||row.payment_provider!=='toss')return {accepted:true,ignored:true};
   // Ordinary payment webhooks are not signed. Never trust their status/amount.
   await applyPayment(row,await payment.get(row.payment_key),'toss-webhook');
   return {accepted:true};
  },
  async paymentDrain(){
   if(!payment)return {state:'disabled',processed:0};
   const rows=await repo.paymentDue(clock()),results=[];
   for(const row of rows){try{await applyPayment(row,await payment.get(row.payment_key),'payment-job');await repo.paymentChecked(row.id,clock());results.push({id:row.id,ok:true});}catch{await repo.paymentChecked(row.id,clock(),true);results.push({id:row.id,ok:false});}}
   return {processed:results.length,failed:results.filter(r=>!r.ok).length};
  }
 };
}
module.exports={lifecycle,view,amounts,activeRefund,blocked};
