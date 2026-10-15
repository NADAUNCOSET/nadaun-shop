'use strict';
const crypto=require('node:crypto');
const {protect}=require('./security.cjs');
const fingerprint=event=>crypto.createHash('sha256').update(JSON.stringify([event.summary,event.description,event.start?.dateTime,event.end?.dateTime])).digest('hex');
const belongs=(event,id)=>event?.extendedProperties?.private?.platform==='nadaun-shop'&&event.extendedProperties.private.orderId===id;
function rentalEvent(row,customer){
 const r=customer.rental;
 if(!r)return null;
 const start=r.start_date+'T'+r.pickup_time+':00+09:00',end=r.end_date+'T'+r.return_time+':00+09:00';
 if(!/^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:00\+09:00$/.test(start)||!Number.isFinite(Date.parse(start))||Date.parse(start)!==r.pickup_at||Date.parse(end)!==r.return_at||r.return_at<=r.pickup_at)throw Error('invalid_rental_schedule');
 const lines=JSON.parse(row.lines_json),state={unfulfilled:'방문 수령 예정',processing:'대여 중',shipped:'반납 완료'}[row.fulfillment]||'처리 확인 필요';
 return {summary:'[나다운샵] '+customer.name+' / '+state,description:'[대여 장비]\n'+lines.map(p=>'• '+p.name+(p.option?' / '+p.option:'')+' // '+p.quantity+'ea').join('\n')+'\n\n방문 수령: '+r.start_date+' '+r.pickup_time+'\n방문 반납: '+r.end_date+' '+r.return_time+'\n예약자: '+customer.name+' / '+customer.phone+'\n주문번호: '+row.id+'\n확정 대여료: '+row.total+'원\n주문관리: https://order.nadaun.co/',start:{dateTime:start,timeZone:'Asia/Seoul'},end:{dateTime:end,timeZone:'Asia/Seoul'},extendedProperties:{private:{platform:'nadaun-shop',orderId:row.id}}};
}
function calendarService({db,dataKey,client,clock=()=>Date.now()}){
 const cipher=protect(dataKey);
 async function sync(row){
  const now=clock(),owner=crypto.randomUUID(),eventId='nadaunshop'+crypto.createHash('sha256').update(row.id).digest('hex');
  await db.query('INSERT INTO shop_calendar_sync(order_id,event_id,status,next_attempt,checked_at,order_version) VALUES(?,?,\'pending\',0,0,-1) ON CONFLICT(order_id) DO NOTHING',[row.id,eventId]);
  const acquired=await db.query('UPDATE shop_calendar_sync SET lease_owner=?,lease_until=? WHERE order_id=? AND lease_until<? RETURNING *',[owner,now+120000,row.id,now]);
  if(!acquired.length)return {state:'busy'};
  const saved=acquired[0];
  async function finish(status,values={}){
   await db.query('UPDATE shop_calendar_sync SET status=?,fingerprint=?,event_url=?,error_code=?,checked_at=?,next_attempt=?,order_version=?,lease_owner=NULL,lease_until=0 WHERE order_id=? AND lease_owner=?',[status,values.fingerprint??saved.fingerprint,values.url??saved.event_url,values.error||null,now,now+(status==='ignored'||status==='canceled'?86400000:status==='synced'?900000:60000),row.version,row.id,owner]);
   return {state:status};
  }
  try{
   const customer=cipher.decrypt(row.customer_cipher);
   if(!customer.rental)return await finish('ignored');
   if(row.state==='PAYMENT_REVIEW')return await finish('review',{error:'payment_review'});
   let event=await client.get(saved.event_id);
   if(event&&!belongs(event,row.id))return await finish('review',{error:'event_identity_mismatch'});
   if(row.state==='CANCELED'){
    if(event&&event.status!=='cancelled')await client.remove(saved.event_id,event.etag);
    return await finish('canceled');
   }
   if(row.state!=='PAID'||row.payment_mode!=='live'||row.payment_provider!=='toss'||!row.paid_at||!row.payment_key)return await finish('ignored');
   const body=rentalEvent(row,customer),desired=fingerprint(body);
   if(customer.rental.return_at<now-2*86400000)return await finish('ignored');
   if(event&&event.status!=='cancelled'&&saved.fingerprint&&fingerprint(event)!==saved.fingerprint)return await finish('review',{error:'calendar_manually_changed'});
   let id=saved.event_id;
   if(event?.status==='cancelled'){
    id=eventId+crypto.randomBytes(6).toString('hex');
    await db.query('UPDATE shop_calendar_sync SET event_id=? WHERE order_id=? AND lease_owner=?',[id,row.id,owner]);event=null;
   }
   if(!event){
    try{event=await client.insert({...body,id});}catch(error){if(error.status!==409)throw error;event=await client.get(id);if(!belongs(event,row.id)||fingerprint(event)!==desired)throw Error('calendar_conflict');}
   }else if(fingerprint(event)!==desired)event=await client.patch(id,body,event.etag);
   if(!belongs(event,row.id)||fingerprint(event)!==desired)throw Error('calendar_response_mismatch');
   const current=(await db.query('SELECT version FROM shop_orders WHERE id=?',[row.id]))[0];
   return await finish(current?.version===row.version?'synced':'pending',{fingerprint:desired,url:event.htmlLink||null});
  }catch(error){return await finish('error',{error:'calendar_or_storage_unavailable'});}
 }
 async function drain(limit=25){
  if(!Number.isSafeInteger(limit)||limit<1||limit>100)throw Error('invalid_batch_limit');
  const rows=await db.query("SELECT o.* FROM shop_orders o LEFT JOIN shop_calendar_sync c ON c.order_id=o.id WHERE o.state IN ('PAID','CANCELED','PAYMENT_REVIEW') AND (c.order_id IS NULL OR c.order_version<>o.version OR c.next_attempt<=?) ORDER BY COALESCE(c.checked_at,0),o.created_at LIMIT ?",[clock(),limit]);
  const states={};for(const row of rows){const result=await sync(row);states[result.state]=(states[result.state]||0)+1;}return {processed:rows.length,states};
 }
 return {sync,drain};
}
module.exports={calendarService,rentalEvent,fingerprint};
