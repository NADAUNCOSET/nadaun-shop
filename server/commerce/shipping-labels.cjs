'use strict';
const crypto=require('node:crypto');
const {ShopError}=require('./security.cjs');
const fulfillment=require('./fulfillment.cjs');
const RANK={REQUEST:0,REGISTERED:0,PRINTED:1,TRANSFERRED:1,PICKUP:2,IN_TRANSIT:3,DLV_START:4,COMPLETED:5};
function labelView(job){return job?{status:job.status,carrier:job.carrier,tracking:job.tracking||null,service_id:job.service_id||null,contract_id:job.contract_id,box:job.box,created_at:job.created_at,checked_at:job.checked_at||null,remote_status:job.remote_status||null}:null;}
function labelPending(customer){return !!customer._admin_shipping_label;}
function shippingLabels({repo,cipher,provider,editable,purchaseCustomer,verifiedForShipping,detailed,clock}){
 function active(){if(!provider?.enabled)throw new ShopError(503,'우리몰 굿스플로 API·택배 계약 연결 후 자동 송장 출력을 사용할 수 있습니다.');}
 async function eligible(id,input){
  const row=await editable(id,input),customer=purchaseCustomer(row);
  if(labelPending(customer))throw new ShopError(409,'이미 송장 접수 이력이 있습니다. 결과 조회 또는 기존 송장 출력을 이용해주세요.');
  if(row.state!=='PAID'||row.payment_mode!=='live'||row.fulfillment!=='unfulfilled'||fulfillment.shipments(row,customer).length||fulfillment.purchaseWorkflow(row,customer)?.stage!=='ready')throw new ShopError(409,'실결제가 확인된 배송 대기 주문을 선택해주세요. 부분 출고·렌탈은 개별 처리해주세요.');
  return {row,customer};
 }
 async function patchJob(id,expected,mutate,actor,action){
  for(let n=0;n<3;n++){
   const row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');
   const customer=purchaseCustomer(row),job=customer._admin_shipping_label;
   if(!job||job.unique_id!==expected)throw new ShopError(409,'송장 접수 이력이 변경되었습니다.');
   const fields=await mutate(row,customer,job);
   if(fields===null)return detailed(row,true);
   try{return detailed(await repo.patch(row,{...fields,customer_cipher:cipher.encrypt(customer)},actor,typeof action==='function'?action(customer):action),true);}catch(error){if(error.status!==409||n===2)throw error;}
  }
 }
 return {
  async labelStatus(){
   if(!provider?.enabled)return {enabled:false,configured:provider?.configured===true,mode:provider?.mode||'test',contracts:[],message:'우리몰 굿스플로 API 연결 대기'};
   const contracts=await provider.contracts();
   return {enabled:true,mode:provider.mode,contracts:contracts.map(c=>({id:c.contractId,carrier:c.transporter,carrier_name:provider.carrierNames[c.transporter],center_name:c.center.name,boxes:c.boxes.map(b=>({code:b.boxSize,name:b.boxSizeName}))})),message:contracts.length?'승인된 택배 계약 연결됨':'사용 가능한 승인 계약이 없습니다.'};
  },
  async labelPreview(input){
   active();
   if(!Array.isArray(input.orders)||!input.orders.length||input.orders.length>25||new Set(input.orders.map(o=>o.id)).size!==input.orders.length)throw new ShopError(400,'중복 없이 1~25개 주문을 선택해주세요.');
   const contract=await provider.contract(input.contract_id,input.box),results=[];
   for(const item of input.orders){
    try{const {row,customer}=await eligible(item.id,item);provider.payload(row,customer,contract,input.box,'preview');results.push({id:row.id,version:row.version,ok:true,name:customer.name,address:[customer.postcode,customer.address,customer.address_detail].filter(Boolean).join(' '),quantity:JSON.parse(row.lines_json).reduce((sum,l)=>sum+l.quantity,0)});}
    catch(error){results.push({id:item.id,ok:false,error:error instanceof ShopError?error.message:'주문을 다시 확인해주세요.'});}
   }
   return {results,contract_id:input.contract_id,box:input.box,carrier:provider.carrierNames[contract.transporter]};
  },
  async labelRegister(input,actor){
   active();if(input.confirmed!==true)throw new ShopError(400,'수령인·배송지·박스 규격을 확인해주세요.');
   const contract=await provider.contract(input.contract_id,input.box),{row,customer}=await eligible(input.id,input),unique='NS-GF-'+crypto.randomUUID();
   const body=provider.payload(row,customer,contract,input.box,unique);
   await verifiedForShipping(row,actor);
   customer._admin_shipping_label={unique_id:unique,status:'pending',contract_id:contract.contractId,center_code:contract.center.code,transporter:contract.transporter,carrier:provider.carrierNames[contract.transporter],box:input.box,created_at:clock(),actor};
   // Reserve before the external call, in the same transaction as the poll queue.
   // Even a timeout or process crash must never automatically POST a second booking.
   await repo.patch(row,{customer_cipher:cipher.encrypt(customer)},actor,'shipping_label_requested',null,{next_attempt:clock()+60000});
   const registered=await provider.register(body);
   return {order:await patchJob(row.id,unique,(_row,_customer,job)=>{job.service_id=registered.serviceId;job.status='registered';return {};},actor,'shipping_label_registered')};
  },
  async labelSync(id,actor='shipping-sync'){
   active();const row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');
   const initial=purchaseCustomer(row)._admin_shipping_label;if(!initial)throw new ShopError(409,'송장 접수 이력이 없습니다.');
   const remote=await provider.lookup(initial.unique_id);
   if(!remote)return {order:await detailed(row,true),pending:true};
   if(remote.uniqueId!==initial.unique_id||remote.centerCode!==initial.center_code||remote.transporter!==initial.transporter||!/^\d{1,40}$/.test(remote.id||'')||(initial.service_id&&initial.service_id!==remote.id))throw new ShopError(409,'주문과 택배 접수 결과가 일치하지 않습니다.');
   const order=await patchJob(id,initial.unique_id,(current,customer,job)=>{
    if(row.state!=='PAID'||current.state!=='PAID'||current.payment_mode!=='live'){job.status='review';job.checked_at=clock();return {};}
    if(remote.invoiceNo&&!/^\d{6,30}$/.test(remote.invoiceNo))throw new ShopError(409,'발급된 송장번호 형식을 확인해주세요.');
    if(job.tracking&&remote.invoiceNo&&job.tracking!==remote.invoiceNo)throw new ShopError(409,'기존 송장번호와 조회 결과가 다릅니다.');
    job.service_id=remote.id;job.checked_at=clock();
    if(!Object.hasOwn(RANK,remote.status)){job.status='review';job.remote_status=remote.status;return {};}
    if((RANK[job.remote_status]??-1)>RANK[remote.status])return {}; // ignore older carrier events
    if(RANK[remote.status]>=1&&!remote.invoiceNo)throw new ShopError(409,'송장 발급 결과를 다시 확인해주세요.');
    job.remote_status=remote.status;job.tracking=remote.invoiceNo||null;
    job.status=RANK[remote.status]>=5?'delivered':RANK[remote.status]>=2?'in_transit':RANK[remote.status]>=1?'printed':'registered';
    const fields=job.tracking?{carrier:job.carrier,tracking:job.tracking}:{};
    if(RANK[remote.status]>=2){
     const history=fulfillment.shipments(current,customer),sid='SH-GF-'+job.unique_id.slice(6);let shipment=history.find(s=>s.id===sid);
     if(!shipment){if(history.length||current.fulfillment!=='unfulfilled')throw new ShopError(409,'기존 출고 내역과 자동 송장 수량을 확인해주세요.');shipment={id:sid,purpose:'original',items:JSON.parse(current.lines_json).map(({id,option,name,quantity})=>({id,option:option||'',name,quantity})),carrier:job.carrier,tracking:job.tracking,created_at:clock(),updated_at:clock(),actor:'goodsflow',updated_by:'goodsflow'};history.push(shipment);}
     if(remote.status==='COMPLETED'&&!shipment.delivered_at){shipment.delivered_at=clock();shipment.delivery_source='goodsflow';shipment.delivery_confirmed_by='goodsflow';}
     customer._admin_shipments=history;fields.fulfillment='shipped';
    }
    return fields;
   },actor,customer=>customer._admin_shipping_label.status==='delivered'?'shipping_label_delivered':'shipping_label_synced');
   if(repo.scheduleShipping)await repo.scheduleShipping(id,order.admin_shipping_label?.status==='delivered'?null:clock()+300000);
   return {order};
  },
  async labelPrint(input,actor='owner'){
   active();
   if(!Array.isArray(input.ids)||!input.ids.length||input.ids.length>25||new Set(input.ids).size!==input.ids.length||typeof input.include_printed!=='boolean')throw new ShopError(400,'출력할 주문 1~25건을 선택해주세요.');
   const jobs=[];
   for(const id of input.ids){const row=await repo.get(id);if(!row)throw new ShopError(404,'주문을 찾을 수 없습니다.');const job=purchaseCustomer(row)._admin_shipping_label;if(row.state!=='PAID'||row.payment_mode!=='live'||!job?.service_id||!['registered','printed','in_transit','delivered'].includes(job.status))throw new ShopError(409,'접수 결과와 결제 상태를 확인한 주문만 출력할 수 있습니다.');if(!input.include_printed&&job.tracking)throw new ShopError(409,'이미 발급된 송장은 재인쇄를 선택해주세요.');await verifiedForShipping(row,actor);jobs.push(job);}
   if(new Set(jobs.map(j=>j.contract_id)).size!==1)throw new ShopError(400,'동일한 택배 계약의 주문끼리 출력해주세요.');
   return provider.print(jobs.map(j=>j.service_id),input.include_printed);
  },
  async labelDrain(){
   if(!provider?.enabled)return {state:'disabled',processed:0};
   const due=await repo.shippingDue(clock()),results=[];
   for(const {order_id:id} of due){try{await repo.scheduleShipping(id,clock()+300000);await this.labelSync(id);results.push({id,ok:true});}catch{results.push({id,ok:false});}}
   return {processed:results.length,results};
  }
 };
}
module.exports={shippingLabels,labelView,labelPending};
