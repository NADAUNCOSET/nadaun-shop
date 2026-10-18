'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {DatabaseSync}=require('node:sqlite');
const {prepareImport,applyImport}=require('../lib/imweb_member_import.cjs');
const {prepareNaverLinks,applyNaverLinks}=require('../lib/naver_member_link.cjs');
const {memberService}=require('../../server/commerce/members.cjs');
const {socialService}=require('../../server/commerce/social.cjs');
const {protect}=require('../../server/commerce/security.cjs');
const key='ab'.repeat(32),clientId='existing-client';
async function fixture(){
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync('server/commerce/schema.sql','utf8'));
 const db={async batch(items){sql.exec('BEGIN');try{const r=items.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return r;}catch(e){sql.exec('ROLLBACK');throw e;}},async query(sql,params=[]){return(await this.batch([{sql,params}]))[0];}};
 const input={source:{site:'rainbowshop.imweb.me',kakao_app_id:'415972',file_sha256:'b'.repeat(64)},rows:['one','two'].map((id,i)=>({'고유키':id,'아이디':id,'이름':'기존 고객','이메일':'same@example.invalid','가입일':'2024-01-02 09:10:11','보유 포인트':'0','NAVER ID':String(12345678+i)}))};
 const plan=prepareImport(input,{dataKey:key,sessionKey:key,kakaoAppId:'415972',kakaoClientId:'a'.repeat(32)});await applyImport(db,plan,key);
 return {sql,db,input,options:{input,dataKey:key,sessionKey:key,clientId,confirmedExistingClientId:clientId},members:memberService({db,repo:{},dataKey:key,sessionKey:key,enabled:true})};
}
test('same-email legacy members retain separate exact Naver identities and reruns preserve profiles',async()=>{
 const f=await fixture(),before=f.sql.prepare('SELECT * FROM shop_members').all();assert.equal((await applyNaverLinks(f.db,f.options)).added,2);assert.equal((await applyNaverLinks(f.db,f.options)).added,0);assert.deepEqual(f.sql.prepare('SELECT * FROM shop_members').all(),before);assert.equal(f.sql.prepare('SELECT count(*) n FROM shop_social_identities').get().n,2);
});
test('actual Naver OAuth flow uses exact legacy subject rather than changed email and does not enroll',async()=>{
 const f=await fixture();await applyNaverLinks(f.db,f.options);const expected=f.sql.prepare('SELECT * FROM shop_members').all().find(m=>protect(key).decrypt(m.profile_cipher).legacy.member_key==='one').id;
 const social=socialService({db:f.db,members:f.members,dataKey:key,sessionKey:key,env:{SHOP_MEMBERS_ENABLED:'true',SHOP_OAUTH_NAVER_ENABLED:'true',SHOP_OAUTH_NAVER_CLIENT_ID:clientId,SHOP_OAUTH_NAVER_CLIENT_SECRET:'fixture'},fetcher:async url=>({ok:true,json:async()=>url.includes('/oauth2.0/token')?{access_token:'fixture-token',token_type:'bearer'}:{resultcode:'00',response:{id:'12345678',email:'changed@example.invalid',name:'다른 표시 이름'}}})});
 const attempt=await social.start('naver'),login=await social.callback('naver',{state:attempt.state,binding:attempt.binding,code:'fixture-code'});assert.equal(login.enrollment,undefined);assert.equal(login.member.id,expected);assert.equal(f.sql.prepare('SELECT count(*) n FROM shop_members').get().n,2);assert.ok(await f.members.authenticate(login.token));
});
test('a different application or changed source fails before identity writes',async()=>{
 const f=await fixture();await assert.rejects(applyNaverLinks(f.db,{...f.options,clientId:'another-app'}),/must match/);f.input.rows[0]['NAVER ID']='999';await assert.rejects(applyNaverLinks(f.db,f.options),/verified source/);assert.equal(f.sql.prepare('SELECT count(*) n FROM shop_social_identities').get().n,0);
});
test('existing identity conflict never reassigns a customer',async()=>{
 const f=await fixture(),members=await f.db.query('SELECT * FROM shop_members'),plan=prepareNaverLinks({...f.options,members,identities:[]});const [a,b]=plan.links;await f.db.query("INSERT INTO shop_social_identities VALUES('naver',?,?,?)",[a.subject_hash,b.member_id,Date.now()]);await assert.rejects(applyNaverLinks(f.db,f.options),/identity conflict/);assert.equal(f.sql.prepare('SELECT count(*) n FROM shop_social_identities').get().n,1);
});
test('closed member stops the complete batch',async()=>{
 const f=await fixture();f.sql.prepare("UPDATE shop_members SET status='closed' WHERE id=(SELECT id FROM shop_members LIMIT 1)").run();await assert.rejects(applyNaverLinks(f.db,f.options),/verified source/);assert.equal(f.sql.prepare('SELECT count(*) n FROM shop_social_identities').get().n,0);
});
test('missing legacy source account stops all writes rather than accepting a partial count',async()=>{
 const f=await fixture();f.sql.prepare('DELETE FROM shop_members WHERE id=(SELECT id FROM shop_members LIMIT 1)').run();await assert.rejects(applyNaverLinks(f.db,f.options),/count mismatch/);assert.equal(f.sql.prepare('SELECT count(*) n FROM shop_social_identities').get().n,0);
});
