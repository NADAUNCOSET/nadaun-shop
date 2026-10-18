'use strict';
const crypto=require('node:crypto');
const {protect,hash}=require('../../server/commerce/security.cjs');
function prepareNaverLinks({members,identities,input,dataKey,sessionKey,clientId,confirmedExistingClientId}){
 if(!clientId||clientId!==confirmedExistingClientId||!input?.source||input.source.site!=='rainbowshop.imweb.me'||!Array.isArray(input.rows))throw Error('Existing Naver application and source must match.');
 const cipher=protect(dataKey),source=new Map(),seen=new Set(),links=[];
 for(const raw of input.rows){const key=String(raw['고유키']||'').trim();if(!key||source.has(key))throw Error('Duplicate source member.');source.set(key,raw);}
 for(const member of members){
  const profile=cipher.decrypt(member.profile_cipher),legacy=profile.legacy,subject=legacy?.pending_identities?.naver;
  if(!subject)continue;
  const raw=source.get(legacy.member_key);
  if(member.status!=='active'||legacy.site!==input.source.site||!raw||legacy.migration?.source_sha256!==input.source.file_sha256||legacy.migration?.fingerprint!==hash(JSON.stringify(raw))||subject!==String(raw['NAVER ID']||'').trim())throw Error('Legacy member does not match verified source.');
  if(typeof subject!=='string'||!subject.length||subject.length>255||/[\x00-\x20\x7f]/.test(subject)||seen.has(subject))throw Error('Invalid or duplicate Naver identity.');seen.add(subject);
  const subjectHash=crypto.createHmac('sha256',sessionKey).update('subject:naver:'+subject).digest('hex');
  if(identities.some(i=>i.provider==='naver'&&((i.subject_hash===subjectHash&&i.member_id!==member.id)||(i.member_id===member.id&&i.subject_hash!==subjectHash))))throw Error('Naver identity conflict; never merge accounts.');
  links.push({provider:'naver',subject_hash:subjectHash,member_id:member.id});
 }
 const expected=input.rows.filter(r=>String(r['NAVER ID']||'').trim()).length;
 if(links.length!==expected)throw Error('Legacy Naver member count mismatch.');
 return {clientId,source_sha256:input.source.file_sha256,links,existing:links.filter(l=>identities.some(i=>i.provider==='naver'&&i.subject_hash===l.subject_hash&&i.member_id===l.member_id)).length};
}
async function applyNaverLinks(db,options){
 const snapshot=async()=>({members:await db.query('SELECT * FROM shop_members'),identities:await db.query('SELECT * FROM shop_social_identities')});
 const before=await snapshot(),plan=prepareNaverLinks({...options,...before}),now=Date.now();
 for(let i=0;i<plan.links.length;i+=20)await db.batch(plan.links.slice(i,i+20).map(l=>({sql:"INSERT INTO shop_social_identities(provider,subject_hash,member_id,created_at) VALUES('naver',?,?,?) ON CONFLICT DO NOTHING",params:[l.subject_hash,l.member_id,now]})));
 const after=await snapshot(),check=prepareNaverLinks({...options,...after});
 if(check.existing!==plan.links.length)throw Error('Naver identity reconciliation failed.');
 const stable=rows=>JSON.stringify([...rows].sort((a,b)=>a.id.localeCompare(b.id)));
 if(stable(before.members)!==stable(after.members))throw Error('Member changed during linking; review before claiming preservation.');
 const oldOther=before.identities.filter(i=>i.provider!=='naver'),newOther=after.identities.filter(i=>i.provider!=='naver');
 if(JSON.stringify(oldOther)!==JSON.stringify(newOther))throw Error('Other provider changed during linking; review required.');
 return {verified:true,total:plan.links.length,added:plan.links.length-plan.existing,already_present:plan.existing,members_preserved:after.members.length,member_profiles_unchanged:true,other_providers_unchanged:true};
}
module.exports={prepareNaverLinks,applyNaverLinks};
