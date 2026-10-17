'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs');
const {DatabaseSync}=require('node:sqlite');
const {prepareImport,applyImport,preflight}=require('../lib/imweb_member_import.cjs');
const {memberService}=require('../../server/commerce/members.cjs');
const {socialService}=require('../../server/commerce/social.cjs');
const {protect}=require('../../server/commerce/security.cjs');
const key='ab'.repeat(32),options={dataKey:key,sessionKey:key,kakaoAppId:'415972',kakaoClientId:'a'.repeat(32)};
const row=(id,extra={})=>({'고유키':id,'아이디':'legacy-'+id,'이름':'기존 고객','이메일':'same@example.invalid','가입일':'2024-01-02 09:10:11','보유 포인트':'0',...extra});
const input=rows=>({source:{site:'rainbowshop.imweb.me',kakao_app_id:'415972',file_sha256:'b'.repeat(64)},rows});
function fixture(){
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync('server/commerce/schema.sql','utf8'));
 const db={async batch(items){sql.exec('BEGIN');try{const rows=items.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return rows;}catch(e){sql.exec('ROLLBACK');throw e;}},async query(sql,params=[]){return(await this.batch([{sql,params}]))[0];}};
 return {db,sql,members:memberService({db,repo:{},dataKey:key,sessionKey:key,enabled:true})};
}
test('migration preserves distinct same-email members, hashes identities, holds Naver and does not manufacture passwords or consent',async()=>{
 const f=fixture(),plan=prepareImport(input([row('one',{'KAKAO ID':'1234567890','NAVER ID':'12345678'}),row('two',{'GOOGLE ID':'123456789012345678901'})]),options);
 assert.equal(plan.counts.pending_naver,1);assert.deepEqual(plan.counts.identities,{kakao:1,google:1,naver:0});await applyImport(f.db,plan,key);
 const rows=f.sql.prepare('SELECT * FROM shop_members').all();assert.equal(rows.length,2);assert.notEqual(rows[0].email_hash,rows[1].email_hash);
 for(const r of rows){assert.equal(r.password_hash,'');assert.equal(r.recovery_hash,'');assert.equal(r.consented_at,0);assert.equal(r.terms_version,'imweb-legacy-unverified');assert.equal(r.profile_cipher.includes('example.invalid'),false);}
 const all=f.sql.prepare('SELECT * FROM shop_social_identities').all();assert.equal(all.length,2);assert.ok(all.every(i=>/^[a-f0-9]{64}$/.test(i.subject_hash)));assert.equal(protect(key).decrypt(rows[0].profile_cipher).legacy.pending_identities.naver,'12345678');
 await assert.rejects(f.members.login({email:'same@example.invalid',password:'any-default-password'}),{status:401});
});
test('the actual OAuth callback finds the imported member and never creates a fresh enrollment',async()=>{
 const f=fixture(),plan=prepareImport(input([row('one',{'KAKAO ID':'1234567890'})]),options);await applyImport(f.db,plan,key);
 const social=socialService({db:f.db,members:f.members,dataKey:key,sessionKey:key,env:{SHOP_MEMBERS_ENABLED:'true',SHOP_OAUTH_KAKAO_ENABLED:'true',SHOP_OAUTH_KAKAO_CLIENT_ID:'fixture',SHOP_OAUTH_KAKAO_CLIENT_SECRET:'fixture'},fetcher:async url=>({ok:true,json:async()=>url.includes('/oauth/token')?{access_token:'fixture-token',token_type:'bearer'}:{id:1234567890,kakao_account:{email:'different@example.invalid',profile:{nickname:'현재 이름'}}}})});
 const start=await social.start('kakao'),login=await social.callback('kakao',{state:start.state,binding:start.binding,code:'fixture-code'});
 assert.equal(login.member.id,plan.records[0].id);assert.equal(login.enrollment,undefined);assert.equal((await f.members.authenticate(login.token)).id,plan.records[0].id);assert.equal(f.sql.prepare('SELECT COUNT(*) n FROM shop_members').get().n,1);await f.members.logout(login.token);
});
test('rerunning migration preserves existing profiles, sessions and points without duplication',async()=>{
 const f=fixture(),source=input([row('one',{'GOOGLE ID':'123456789012345678901','보유 포인트':'2500'})]),plan=prepareImport(source,options);await applyImport(f.db,plan,key);
 const old=f.sql.prepare('SELECT profile_cipher FROM shop_members').get().profile_cipher,subject=plan.records[0].identities[0].subject_hash,login=await f.members.socialLogin('google',subject);
 const second=await applyImport(f.db,prepareImport(source,options),key);assert.equal(second.created,0);assert.equal(second.already_present,1);assert.equal(f.sql.prepare('SELECT profile_cipher FROM shop_members').get().profile_cipher,old);assert.equal(f.sql.prepare('SELECT SUM(amount) n FROM shop_points').get().n,2500);assert.ok(await f.members.authenticate(login.token));
});
test('any existing identity conflict prevents every write instead of merging accounts',async()=>{
 const f=fixture(),original=prepareImport(input([row('old',{'KAKAO ID':'1234567890'})]),options);await applyImport(f.db,original,key);
 const plan=prepareImport(input([row('new'),row('conflict',{'KAKAO ID':'1234567890'})]),options);await assert.rejects(applyImport(f.db,plan,key),/identity conflicts/);assert.equal(f.sql.prepare('SELECT COUNT(*) n FROM shop_members').get().n,1);
});
test('changed source, closed members, duplicated provider IDs and another Kakao app fail closed',async()=>{
 const f=fixture(),source=input([row('one')]),plan=prepareImport(source,options);await applyImport(f.db,plan,key);
 await assert.rejects(preflight(f.db,prepareImport(input([row('one',{'이름':'변경된 고객'})]),options),key),/conflicts/);
 f.sql.prepare("UPDATE shop_members SET status='closed'").run();await assert.rejects(preflight(f.db,plan,key),/conflicts/);
 assert.throws(()=>prepareImport(input([row('one',{'KAKAO ID':'1234567890'}),row('two',{'KAKAO ID':'1234567890'})]),options),/Duplicate source social/);
 assert.throws(()=>prepareImport(source,{...options,kakaoAppId:'other'}),/Existing Kakao app/);
});
test('failed database batch rolls back its partial member and can be safely rerun',async()=>{
 const f=fixture(),plan=prepareImport(input([row('one',{'KAKAO ID':'1234567890'})]),options),real=f.db.batch.bind(f.db);let fail=true;
 f.db.batch=items=>{if(fail&&items.some(s=>s.sql.startsWith('INSERT INTO shop_members'))){fail=false;return real([...items,{sql:'INSERT INTO missing_table VALUES(1)',params:[]}]);}return real(items);};
 await assert.rejects(applyImport(f.db,plan,key));assert.equal(f.sql.prepare('SELECT COUNT(*) n FROM shop_members').get().n,0);assert.equal((await applyImport(f.db,plan,key)).verified,true);
});
