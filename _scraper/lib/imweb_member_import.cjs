'use strict';
// Offline owner-authorized migration. Never match or merge accounts by email.
const crypto=require('node:crypto');
const {protect,hash,adminEmail}=require('../../server/commerce/security.cjs');
function prepareImport(input,{dataKey,sessionKey,kakaoAppId,kakaoClientId,clock=()=>Date.now()}){
 const digest=value=>crypto.createHmac('sha256',sessionKey).update(value).digest('hex'),cipher=protect(dataKey);
 const source=input?.source;
 if(!source||source.site!=='rainbowshop.imweb.me'||!/^[a-f0-9]{64}$/.test(source.file_sha256||'')||!Array.isArray(input.rows)||!input.rows.length)throw Error('Invalid migration source.');
 if(kakaoAppId!=='415972'||source.kakao_app_id!==kakaoAppId||!/^[a-f0-9]{32}$/i.test(kakaoClientId||''))throw Error('Existing Kakao app must be confirmed before import.');
 const seen=new Set(),identities=new Set(),records=[],now=clock();
 const text=value=>typeof value==='string'?value.trim():'';
 const counts={members:0,identities:{kakao:0,google:0,naver:0},pending_naver:0,without_linked_identity:0,points:0};
 for(const raw of input.rows){
  const key=text(raw['고유키']),name=text(raw['이름']),email=adminEmail(raw['이메일']);
  if(!key||key.length>255||seen.has(key)||!name||name.length>60||!email||/[\x00-\x1f\x7f]/.test(name))throw Error('Invalid or duplicate source member.');seen.add(key);
  const date=text(raw['가입일']);if(!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(date))throw Error('Invalid source registration date.');
  const createdAt=Date.parse(date.replace(' ','T')+'+09:00');if(!Number.isSafeInteger(createdAt)||createdAt>now)throw Error('Invalid source registration date.');
  const amount=text(raw['보유 포인트']).replaceAll(',','');if(!/^[0-9]+$/.test(amount))throw Error('Invalid source points.');
  const balance=Number(amount);if(!Number.isSafeInteger(balance)||balance<0||balance>100000000)throw Error('Invalid source points.');
  const stable=digest('imweb-member:'+source.site+':'+key),uuid=stable.slice(0,8)+'-'+stable.slice(8,12)+'-5'+stable.slice(13,16)+'-a'+stable.slice(17,20)+'-'+stable.slice(20,32),id='NM-'+uuid;
  const linked=[];
  for(const [provider,field] of [['kakao','KAKAO ID'],['google','GOOGLE ID']]){
   const subject=text(raw[field]);if(!subject)continue;
   if(!(provider==='kakao'?/^[1-9][0-9]{0,15}$/:/^[0-9]{21}$/).test(subject))throw Error('Invalid exported provider identifier.');
   const subjectHash=digest('subject:'+provider+':'+subject),unique=provider+':'+subjectHash;
   if(identities.has(unique))throw Error('Duplicate source social identity.');identities.add(unique);
   linked.push({provider,subject_hash:subjectHash});counts.identities[provider]++;
  }
  const naver=text(raw['NAVER ID']);if(naver)counts.pending_naver++;
  const fingerprint=hash(JSON.stringify(raw));
  const profile={name,email,email_verified:false,phone:text(raw['연락처']),postcode:text(raw['우편번호']),address:text(raw['주소']),address_detail:text(raw['상세주소']),
   legacy:{source:'imweb',site:source.site,member_key:key,login_id:text(raw['아이디']),registered_at:date,
    migration:{source_sha256:source.file_sha256,fingerprint,imported_at:now,kakao_app_id:kakaoAppId,kakao_client_id_hash:hash(kakaoClientId)},
    // Historical flags are retained as historical data, never current-policy consent.
    historical_consents:{sms:text(raw['메시지 수신 동의']),email:text(raw['E-Mail 수신 동의']),third_party:text(raw['개인정보제3자제공동의'])},
    pending_identities:{...(naver?{naver}:{}),...(text(raw['FACEBOOK ID'])?{facebook:text(raw['FACEBOOK ID'])}: {})}}};
  records.push({id,email_hash:'legacy:'+digest('imweb-login:'+source.site+':'+key),owner_hash:hash('member:'+id),profile_cipher:cipher.encrypt(profile),fingerprint,created_at:createdAt,identities:linked,balance});
  counts.members++;counts.points+=balance;if(!linked.length)counts.without_linked_identity++;
 }
 return {source_sha256:source.file_sha256,records,counts,created_at:now};
}
async function preflight(db,plan,dataKey){
 const members=await db.query('SELECT * FROM shop_members'),identities=await db.query('SELECT * FROM shop_social_identities'),cipher=protect(dataKey);
 const byId=new Map(members.map(m=>[m.id,m])),byIdentity=new Map(identities.map(i=>[i.provider+':'+i.subject_hash,i.member_id]));
 let existing=0;
 for(const record of plan.records){
  const row=byId.get(record.id);
  if(row){
   const profile=cipher.decrypt(row.profile_cipher);
   if(row.status!=='active'||row.email_hash!==record.email_hash||profile.legacy?.migration?.fingerprint!==record.fingerprint)throw Error('Existing member conflicts with migration; nothing overwritten.');
   existing++;
  }
  if(members.some(m=>m.id!==record.id&&(m.email_hash===record.email_hash||m.owner_hash===record.owner_hash)))throw Error('Existing member key conflicts with migration.');
  for(const identity of record.identities){
   const owner=byIdentity.get(identity.provider+':'+identity.subject_hash);
   if(owner&&owner!==record.id||identities.some(i=>i.member_id===record.id&&i.provider===identity.provider&&i.subject_hash!==identity.subject_hash))throw Error('Existing social identity conflicts with migration; no merge allowed.');
  }
 }
 return {existing,new_members:plan.records.length-existing};
}
async function applyImport(db,plan,dataKey,{onProgress=()=>{}}={}){
 const before=await preflight(db,plan,dataKey);
 for(let i=0;i<plan.records.length;i+=10){
  const batch=[];
  for(const r of plan.records.slice(i,i+10)){
   // Blank credentials deliberately cannot authenticate. No shared/default password.
   batch.push({sql:"INSERT INTO shop_members(id,email_hash,owner_hash,profile_cipher,password_hash,recovery_hash,terms_version,consented_at,created_at,status) VALUES(?,?,?,?,'','','imweb-legacy-unverified',0,?,'active') ON CONFLICT(id) DO NOTHING",params:[r.id,r.email_hash,r.owner_hash,r.profile_cipher,r.created_at]});
   for(const identity of r.identities)batch.push({sql:'INSERT INTO shop_social_identities(provider,subject_hash,member_id,created_at) VALUES(?,?,?,?) ON CONFLICT DO NOTHING',params:[identity.provider,identity.subject_hash,r.id,plan.created_at]});
   if(r.balance)batch.push({sql:"INSERT INTO shop_points(id,member_id,amount,reason,kind,request_key,fingerprint,actor,created_at) VALUES(?,?,?,'기존 아임웹 적립금 이전','adjustment',?,?,'imweb-migration',?) ON CONFLICT(request_key) DO NOTHING",params:[crypto.randomUUID(),r.id,r.balance,'imweb-balance:'+r.id,hash(r.id+':'+r.balance),plan.created_at]});
  }
  await db.batch(batch);onProgress(Math.min(i+10,plan.records.length));
 }
 const result=await verifyImport(db,plan,dataKey);return {...result,created:before.new_members,already_present:before.existing};
}
async function verifyImport(db,plan,dataKey){
 const check=await preflight(db,plan,dataKey);if(check.existing!==plan.records.length)throw Error('Member reconciliation failed.');
 const ids=new Set(plan.records.map(r=>r.id)),actual=await db.query('SELECT * FROM shop_social_identities');
 const linked=actual.filter(i=>ids.has(i.member_id));
 for(const r of plan.records)for(const i of r.identities)if(!linked.some(a=>a.provider===i.provider&&a.subject_hash===i.subject_hash&&a.member_id===r.id))throw Error('Social identity reconciliation failed.');
 const points=await db.query("SELECT member_id,amount,fingerprint FROM shop_points WHERE actor='imweb-migration'");
 for(const r of plan.records)if(r.balance&&!points.some(p=>p.member_id===r.id&&p.amount===r.balance&&p.fingerprint===hash(r.id+':'+r.balance)))throw Error('Points reconciliation failed.');
 return {verified:true,...plan.counts,linked_identities:linked.length};
}
module.exports={prepareImport,preflight,applyImport,verifyImport};
