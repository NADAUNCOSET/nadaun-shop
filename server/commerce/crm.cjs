'use strict';
const crypto=require('node:crypto');
const {ShopError,protect}=require('./security.cjs');
const DAY=86400000;
const normalize=v=>String(v||'').normalize('NFKC').toLocaleLowerCase('ko-KR').replace(/\s/g,'');
const segments=['all','new','active','no-orders','buyers','repeat','google','kakao','naver'];
const memberId=value=>{if(!/^NM-[a-f0-9-]{36}$/.test(value||''))throw new ShopError(400,'고객을 확인해주세요.');return value;};
const clean=(v,max)=>typeof v==='string'&&v.length<=max&&!/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(v)?v.trim():null;
function crmService({db,dataKey,testing=false,clock=()=>Date.now()}){
 const cipher=protect(dataKey),mode=testing?'test':'live';
 const base=`SELECT m.id,m.profile_cipher,m.created_at,m.consented_at,m.terms_version,
  COALESCE(a.last_login_at,(SELECT MAX(s.created_at) FROM shop_member_sessions s WHERE s.member_id=m.id)) AS last_login_at,
  COALESCE(a.login_count,0) AS login_count,
  COALESCE((SELECT group_concat(i.provider) FROM shop_social_identities i WHERE i.member_id=m.id),'') AS providers,
  COALESCE((SELECT SUM(p.amount) FROM shop_points p WHERE p.member_id=m.id),0) AS balance,
  (SELECT COUNT(*) FROM shop_orders o WHERE o.customer_hash=m.owner_hash AND (o.payment_mode IS NULL OR o.payment_mode='${mode}')) AS order_count,
  (SELECT COUNT(*) FROM shop_orders o WHERE o.customer_hash=m.owner_hash AND o.state='PAID' AND o.payment_mode='${mode}') AS paid_count,
  COALESCE((SELECT SUM(o.total) FROM shop_orders o WHERE o.customer_hash=m.owner_hash AND o.state='PAID' AND o.payment_mode='${mode}'),0) AS paid_total,
  c.private_cipher AS crm_cipher,COALESCE(c.version,0) AS crm_version
  FROM shop_members m LEFT JOIN shop_member_activity a ON a.member_id=m.id LEFT JOIN shop_member_crm c ON c.member_id=m.id WHERE m.status='active'`;
 function customer(row,detail=false){
  const p=cipher.decrypt(row.profile_cipher),c=row.crm_cipher?cipher.decrypt(row.crm_cipher):{};
  return {id:row.id,name:p.name||'',email:p.email||'',phone:p.phone||'',created_at:row.created_at,
   source:p.legacy?'migrated':'shop',providers:row.providers?row.providers.split(',').sort():[],last_login_at:row.last_login_at||null,
   login_count:row.login_count,balance:row.balance,order_count:row.order_count,paid_count:row.paid_count,paid_total:row.paid_total,
   tags:Array.isArray(c.tags)?c.tags:[],note:detail?c.note||'':undefined,version:row.crm_version,
   // Historical migration flags are evidence only, never permission to send a new campaign.
   marketing_eligible:false,...(detail?{address:[p.postcode,p.address,p.address_detail].filter(Boolean).join(' '),
    historical_consents:p.legacy?.historical_consents||null,terms_version:row.terms_version,consented_at:row.consented_at}: {})};
 }
 function filters(input={}){
  const search=clean(input.search||'',100),segment=input.segment||'all',sort=input.sort||'recent',page=Number(input.page||1),pageSize=Number(input.pageSize||25);
  if(search===null||!segments.includes(segment)||!['recent','joined','spent'].includes(sort)||!Number.isSafeInteger(page)||page<1||page>100000||![25,50,100].includes(pageSize))throw new ShopError(400,'고객 조회 조건을 확인해주세요.');
  return {search,segment,sort,page,pageSize};
 }
 function whereSegment(segment){
  if(['google','kakao','naver'].includes(segment))return {sql:' AND EXISTS(SELECT 1 FROM shop_social_identities i WHERE i.member_id=m.id AND i.provider=?)',params:[segment]};
  if(segment==='new')return {sql:' AND m.created_at>=?',params:[clock()-30*DAY]};
  if(segment==='active')return {sql:' AND COALESCE(a.last_login_at,(SELECT MAX(s.created_at) FROM shop_member_sessions s WHERE s.member_id=m.id),0)>=?',params:[clock()-30*DAY]};
  const orders=`SELECT COUNT(*) FROM shop_orders o WHERE o.customer_hash=m.owner_hash AND (o.payment_mode IS NULL OR o.payment_mode='${mode}')`;
  const paid=`SELECT COUNT(*) FROM shop_orders o WHERE o.customer_hash=m.owner_hash AND o.state='PAID' AND o.payment_mode='${mode}'`;
  if(segment==='no-orders')return {sql:` AND (${orders})=0`,params:[]};
  if(segment==='buyers'||segment==='repeat')return {sql:` AND (${paid})>=?`,params:[segment==='repeat'?2:1]};
  return {sql:'',params:[]};
 }
 async function list(input={}){
  const f=filters(input),w=whereSegment(f.segment),ordering={recent:'last_login_at DESC,m.created_at DESC,m.id DESC',joined:'m.created_at DESC,m.id DESC',spent:'paid_total DESC,m.created_at DESC,m.id DESC'}[f.sort];
  let rows,total;
  if(f.search){
   const matches=[],q=normalize(f.search),digits=f.search.replace(/[^0-9]/g,'');let cursor='',scanned=0;
   do{const batch=await db.query(base+w.sql+' AND m.id>? ORDER BY m.id LIMIT 500',[...w.params,cursor]);scanned+=batch.length;
    if(scanned>10000)throw new ShopError(413,'검색 대상이 많습니다. 고객 분류를 좁혀 다시 검색해주세요.');
    for(const row of batch){const c=customer(row);if([c.name,c.email,c.id,...c.tags].some(v=>normalize(v).includes(q))||digits.length>=3&&c.phone.replace(/[^0-9]/g,'').includes(digits))matches.push(c);}
    if(batch.length<500)break;cursor=batch.at(-1).id;
   }while(true);
   matches.sort((a,b)=>(f.sort==='spent'?b.paid_total-a.paid_total:f.sort==='recent'?(b.last_login_at||0)-(a.last_login_at||0):0)||b.created_at-a.created_at||b.id.localeCompare(a.id));
   total=matches.length;rows=matches.slice((f.page-1)*f.pageSize,f.page*f.pageSize);
  }else{
   total=(await db.query('SELECT COUNT(*) AS n FROM shop_members m LEFT JOIN shop_member_activity a ON a.member_id=m.id WHERE m.status=\'active\''+w.sql,w.params))[0].n;
   rows=(await db.query(base+w.sql+' ORDER BY '+ordering+' LIMIT ? OFFSET ?',[...w.params,f.pageSize,(f.page-1)*f.pageSize])).map(r=>customer(r));
  }
  return {members:rows,total,page:f.page,pages:Math.max(1,Math.ceil(total/f.pageSize)),pageSize:f.pageSize,filters:f,testing};
 }
 async function overview(){
  const [summary,providers,recent,orders,campaigns]=await Promise.all([
   db.query(`SELECT COUNT(*) AS members,SUM(CASE WHEN m.created_at>=? THEN 1 ELSE 0 END) AS new_members,SUM(CASE WHEN COALESCE(a.last_login_at,(SELECT MAX(s.created_at) FROM shop_member_sessions s WHERE s.member_id=m.id),0)>=? THEN 1 ELSE 0 END) AS active_members FROM shop_members m LEFT JOIN shop_member_activity a ON a.member_id=m.id WHERE m.status='active'`,[clock()-30*DAY,clock()-30*DAY]),
   db.query("SELECT i.provider,COUNT(*) AS count FROM shop_social_identities i JOIN shop_members m ON m.id=i.member_id WHERE m.status='active' GROUP BY i.provider"),
   list({sort:'recent',pageSize:25}),
   db.query(`SELECT COUNT(*) AS orders,SUM(CASE WHEN state='REQUESTED' THEN 1 ELSE 0 END) AS requested,SUM(CASE WHEN state='PAID' THEN 1 ELSE 0 END) AS paid,COALESCE(SUM(CASE WHEN state='PAID' THEN total ELSE 0 END),0) AS paid_total FROM shop_orders WHERE payment_mode IS NULL OR payment_mode=?`,[mode]),
   db.query("SELECT COUNT(*) AS n FROM shop_marketing_drafts WHERE status='draft'")
  ]);
  return {summary:{...summary[0],...orders[0],campaign_drafts:campaigns[0].n,marketing_eligible:0},providers,recent:recent.members.slice(0,6),testing,checked_at:clock()};
 }
 async function detail(id){
  memberId(id);const row=(await db.query(base+' AND m.id=?',[id]))[0];if(!row)throw new ShopError(404,'고객을 찾을 수 없습니다.');
  const orders=await db.query(`SELECT o.id,o.state,o.total,o.created_at,o.payment_mode,o.fulfillment,o.lines_json FROM shop_orders o JOIN shop_members m ON m.owner_hash=o.customer_hash WHERE m.id=? AND (o.payment_mode IS NULL OR o.payment_mode=?) ORDER BY o.created_at DESC,o.id DESC LIMIT 101`,[id,mode]);
  const points=await db.query('SELECT amount,reason,kind,created_at FROM shop_points WHERE member_id=? ORDER BY created_at DESC,id DESC LIMIT 50',[id]);
  return {member:customer(row,true),orders:orders.slice(0,100).map(o=>({id:o.id,state:o.state,total:o.total,created_at:o.created_at,fulfillment:o.fulfillment,product:JSON.parse(o.lines_json)[0]?.name||'',payment_mode:o.payment_mode})),has_more_orders:orders.length>100,points};
 }
 async function saveNote(input,actor){
  const id=memberId(input.id),note=clean(input.note??'',2000),tags=input.tags,version=input.version;
  if(note===null||!Array.isArray(tags)||tags.length>10||tags.some(t=>!clean(t,30))||!Number.isSafeInteger(version)||version<0)throw new ShopError(400,'메모와 태그를 확인해주세요.');
  const value=cipher.encrypt({note,tags:[...new Set(tags.map(t=>t.trim()))]}),now=clock();
  const rows=await db.batch([{sql:`INSERT INTO shop_member_crm(member_id,private_cipher,version,updated_at,updated_by) SELECT id,?,1,?,? FROM shop_members WHERE id=? AND status='active' AND ?=0 ON CONFLICT(member_id) DO UPDATE SET private_cipher=excluded.private_cipher,version=shop_member_crm.version+1,updated_at=excluded.updated_at,updated_by=excluded.updated_by WHERE shop_member_crm.version=? RETURNING version`,params:[value,now,actor,id,version,version]}]);
  // Existing records with a nonzero version use a guarded update instead of the INSERT branch.
  if(!rows[0].length&&version>0){const changed=await db.query('UPDATE shop_member_crm SET private_cipher=?,version=version+1,updated_at=?,updated_by=? WHERE member_id=? AND version=? AND EXISTS(SELECT 1 FROM shop_members WHERE id=? AND status=\'active\') RETURNING version',[value,now,actor,id,version,id]);if(changed.length)return {saved:true,version:changed[0].version};}
  if(!rows[0].length)throw new ShopError(409,'다른 곳에서 변경됐습니다. 고객 정보를 새로고침해주세요.');return {saved:true,version:rows[0][0].version};
 }
 async function campaigns(){const rows=await db.query('SELECT * FROM shop_marketing_drafts ORDER BY updated_at DESC,id DESC LIMIT 200');return {campaigns:rows.map(r=>({id:r.id,...cipher.decrypt(r.private_cipher),status:r.status,version:r.version,created_at:r.created_at,updated_at:r.updated_at})),delivery_enabled:false};}
 async function saveCampaign(input,actor){
  const name=clean(input.name,100),body=clean(input.body||'',4000),channel=input.channel,segment=input.segment,status=input.status||'draft',version=input.version??0;
  if(!name||body===null||!['email','kakao','sms'].includes(channel)||!segments.includes(segment)||!['draft','archived'].includes(status)||!Number.isSafeInteger(version)||version<0)throw new ShopError(400,'캠페인 내용을 확인해주세요.');
  let url;try{url=new URL(input.url);if(url.origin!=='https://shop.nadaun.co'||url.username||url.password||url.href.length>1000)throw Error();}catch{throw new ShopError(400,'캠페인 링크는 https://shop.nadaun.co 주소를 사용해주세요.');}
  const id=input.id||'MC-'+crypto.randomUUID();if(!/^MC-[a-f0-9-]{36}$/.test(id))throw new ShopError(400,'캠페인을 확인해주세요.');
  const data=cipher.encrypt({name,body,channel,segment,url:url.href}),now=clock();
  const changed=version===0?await db.query("INSERT INTO shop_marketing_drafts(id,private_cipher,status,version,created_by,updated_by,created_at,updated_at) VALUES(?,?,?,1,?,?,?,?) ON CONFLICT(id) DO NOTHING RETURNING version",[id,data,status,actor,actor,now,now]):await db.query('UPDATE shop_marketing_drafts SET private_cipher=?,status=?,version=version+1,updated_by=?,updated_at=? WHERE id=? AND version=? RETURNING version',[data,status,actor,now,id,version]);
  if(!changed.length){const current=(await db.query('SELECT private_cipher,status,version,updated_by FROM shop_marketing_drafts WHERE id=?',[id]))[0];if(current&&current.version===version+1&&current.updated_by===actor&&current.status===status&&JSON.stringify(cipher.decrypt(current.private_cipher))===JSON.stringify({name,body,channel,segment,url:url.href}))return {saved:true,id,version:current.version,sent:0,duplicate:true};throw new ShopError(409,'캠페인이 변경됐습니다. 새로고침 후 다시 저장해주세요.');}return {saved:true,id,version:changed[0].version,sent:0};
 }
 return {list,overview,detail,saveNote,campaigns,saveCampaign};
}
module.exports={crmService};
