const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const {DatabaseSync}=require('node:sqlite');
const {crmService}=require('../../server/commerce/crm.cjs');
const {memberService}=require('../../server/commerce/members.cjs');
const {memberEndpoint}=require('../../server/commerce/member-http.cjs');
const {protect,hash,sessions}=require('../../server/commerce/security.cjs');
const key='cd'.repeat(32),now=Date.parse('2026-10-18T05:00:00Z');
function fixture(){
 const sql=new DatabaseSync(':memory:');sql.exec(fs.readFileSync('server/commerce/schema.sql','utf8'));
 const db={async batch(statements){sql.exec('BEGIN');try{const r=statements.map(s=>sql.prepare(s.sql).all(...(s.params||[])));sql.exec('COMMIT');return r;}catch(e){sql.exec('ROLLBACK');throw e;}},async query(s,p=[]){return(await this.batch([{sql:s,params:p}]))[0];}};
 const repo={async limit(){}},crm=crmService({db,dataKey:key,clock:()=>now}),members=memberService({db,repo,dataKey:key,sessionKey:key,enabled:true,clock:()=>now});
 function add(n,extra={}){const id='NM-'+crypto.randomUUID();sql.prepare("INSERT INTO shop_members VALUES(?,?,?,?,?,'','legacy',0,?,'active',NULL)").run(id,'hash-'+n,hash('member:'+id),protect(key).encrypt({name:'고객 '+n,email:'person'+n+'@example.invalid',phone:'0101234'+String(n).padStart(4,'0'),...extra}),'',now-n*86400000);return id;}
 function order(id,{total=30000,mode='live',state='PAID',owner}={}){const oid='NS-'+crypto.randomUUID();sql.prepare("INSERT INTO shop_orders(id,customer_hash,request_key,fingerprint,state,customer_cipher,lines_json,total,shipping,confirm_key,payment_mode,created_at,updated_at) VALUES(?,?,?,?,?,?,?, ?,0,?,?,?,?)").run(oid,owner||hash('member:'+id),crypto.randomUUID(),'fixture',state,protect(key).encrypt({name:'고객'}),JSON.stringify([{name:'검증 상품',quantity:1}]),total,crypto.randomUUID(),mode,now,now);return oid;}
 return {sql,db,crm,members,repo,add,order};
}
test('all 360 members are paginated without omissions; normalized search finds old members',async()=>{
 const f=fixture(),ids=Array.from({length:360},(_,i)=>f.add(i));const found=[];
 for(let page=1;page<=15;page++){const v=await f.crm.list({page});assert.equal(v.total,360);found.push(...v.members.map(m=>m.id));}
 assert.equal(new Set(found).size,360);assert.ok(found.includes(ids[359]));
 const v=await f.crm.list({search:' PERSON359@EXAMPLE.INVALID '});assert.equal(v.total,1);assert.equal(v.members[0].id,ids[359]);assert.equal((await f.crm.list({search:'010-1234-0359'})).total,1);
 assert.doesNotMatch(JSON.stringify(v),/profile_cipher|password_hash|owner_hash|email_hash|subject_hash|member_key/);
});
test('customer orders join by member owner only, not matching names or email; test payments excluded',async()=>{
 const f=fixture(),id=f.add(1),other=f.add(2),a=f.order(id);f.order(other);f.order(id,{mode:'test'});f.order(id,{owner:hash('guest'),total:999});
 const v=await f.crm.detail(id);assert.deepEqual(v.orders.map(o=>o.id),[a]);assert.equal(v.member.paid_total,30000);assert.equal(v.member.order_count,1);assert.equal((await f.crm.list({segment:'buyers'})).total,2);
});
test('login survives logout in CRM activity; unknown legacy login dates stay unknown',async()=>{
 const f=fixture(),id=f.add(1);assert.equal((await f.crm.detail(id)).member.last_login_at,null);
 const joined=await f.members.signup({name:'New member',email:'new@example.invalid',password:'a-long-secure-test-password',age14:true,terms:true,privacy:true});await f.members.logout(joined.token);
 assert.equal((await f.crm.detail(joined.member.id)).member.last_login_at,now);assert.equal((await f.crm.list({segment:'active'})).total,1);
});
test('social provider segments, new and repeat buyer cohorts have actual database evidence',async()=>{
 const f=fixture(),a=f.add(1),b=f.add(100);f.sql.prepare('INSERT INTO shop_social_identities VALUES(?,?,?,?)').run('google','ab'.repeat(32),a,now);f.order(b);f.order(b);
 assert.equal((await f.crm.list({segment:'google'})).members[0].id,a);assert.equal((await f.crm.list({segment:'new'})).members[0].id,a);assert.equal((await f.crm.list({segment:'repeat'})).members[0].id,b);
 const v=await f.crm.overview();assert.equal(v.summary.members,2);assert.equal(v.summary.paid_total,60000);assert.equal(v.providers[0].count,1);
});
test('notes encrypt private text and guard concurrent edits; withdrawal erases CRM profile metadata',async()=>{
 const f=fixture(),id=f.add(1);await f.crm.saveNote({id,note:'private-note',tags:['camera'],version:0},'owner');
 assert.doesNotMatch(f.sql.prepare('SELECT private_cipher FROM shop_member_crm').get().private_cipher,/private-note|camera/);
 await assert.rejects(f.crm.saveNote({id,note:'stale',tags:[],version:0},'owner'),{status:409});
 await f.crm.saveNote({id,note:'edited',tags:['VIP'],version:1},'owner');assert.equal((await f.crm.detail(id)).member.note,'edited');assert.equal((await f.crm.list({search:'VIP'})).total,1);
 await f.members.close({id,owner:hash('member:'+id),authenticated_at:now},{confirmed:true});assert.equal(f.sql.prepare('SELECT COUNT(*) n FROM shop_member_crm').get().n,0);await assert.rejects(f.crm.detail(id),{status:404});
});
test('historical consent is not treated as current marketing consent and campaign saves never send',async()=>{
 const f=fixture(),id=f.add(1,{legacy:{historical_consents:{email:'Y',sms:'Y'},pending_identities:{naver:'private-old-id'}}});assert.equal((await f.crm.detail(id)).member.marketing_eligible,false);assert.doesNotMatch(JSON.stringify(await f.crm.detail(id)),/private-old-id/);
 const input={id:'MC-'+crypto.randomUUID(),name:'Welcome',body:'hello',channel:'email',segment:'no-orders',url:'https://shop.nadaun.co/?utm_campaign=welcome'};const saved=await f.crm.saveCampaign(input,'owner');assert.equal(saved.sent,0);assert.equal((await f.crm.campaigns()).delivery_enabled,false);
 await assert.rejects(f.crm.saveCampaign({...input,url:'https://evil.example/'},'owner'),{status:400});assert.equal((await f.crm.saveCampaign(input,'owner')).duplicate,true);await assert.rejects(f.crm.saveCampaign({...input,body:'conflicting retry'},'owner'),{status:409});
 await f.crm.saveCampaign({...input,version:1,status:'archived'},'owner');assert.equal((await f.crm.campaigns()).campaigns[0].status,'archived');
});
async function call(handler,action,{method='GET',body={},cookie='',origin='https://order.nadaun.co'}={}){const res={headers:{},setHeader(k,v){this.headers[k]=v;},status(s){this.code=s;return this;},json(v){this.body=v;return this;}};await handler({url:'/api/members?action='+action,method,body,headers:{cookie,origin}},res);return res;}
test('all CRM reads and writes require authenticated admin and write origin validation',async()=>{
 const f=fixture(),handler=memberEndpoint({...f,sessionKey:key,adminPasswordEmail:'owner@example.invalid'}),cookie='__Host-nadaun-admin='+sessions(key).issue('owner@example.invalid','admin',3600);
 for(const [action,method] of [['admin-overview','GET'],['admin-customers','POST'],['admin-customer','GET'],['admin-campaigns','GET'],['admin-campaign-save','POST'],['admin-customer-note','POST']])assert.equal((await call(handler,action,{method})).code,401);
 assert.equal((await call(handler,'admin-customers',{method:'POST',cookie})).code,200);assert.equal((await call(handler,'admin-customers',{method:'POST',cookie,origin:'https://evil.example'})).code,403);
 const bad='__Host-nadaun-admin='+sessions(key).issue('someone@example.invalid','admin',3600);assert.equal((await call(handler,'admin-overview',{cookie:bad})).code,401);
 const response=await call(handler,'admin-overview',{cookie});assert.equal(response.code,200);assert.equal(response.headers['Cache-Control'],'no-store');
});
test('bad pagination, provider, member id and campaign URL fail without issuing arbitrary SQL',async()=>{
 const f=fixture();for(const input of [{page:-1},{pageSize:9999},{segment:'unknown'},{sort:'DROP TABLE'},{search:'x'.repeat(101)}])await assert.rejects(f.crm.list(input),{status:400});await assert.rejects(f.crm.detail("' OR 1=1"),{status:400});
});
