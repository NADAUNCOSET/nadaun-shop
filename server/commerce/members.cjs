'use strict';
const crypto=require('node:crypto');
const {promisify}=require('node:util');
const {ShopError,protect,hash,random,passwordMatches,adminEmail}=require('./security.cjs');
const scrypt=promisify(crypto.scrypt);
const VERSION='2026-10-17';
function deliveryContact(raw,contactOnly=false){
 const result={};
 for(const [key,min,max] of [['name',2,60],['phone',9,20],...(!contactOnly?[['postcode',5,5],['address',5,160],['address_detail',1,100]]:[])]){
  const value=typeof raw?.[key]==='string'?raw[key].trim():'';
  result[key]=value.length>=min&&value.length<=max&&!/[\x00-\x1f\x7f<>]/.test(value)?value:'';
 }
 if(!/^0[\d -]{8,19}$/.test(result.phone))result.phone='';
 if(!contactOnly&&!/^\d{5}$/.test(result.postcode))result.postcode='';
 return result;
}
function memberService({db,repo,dataKey,sessionKey,enabled=false,earnBasisPoints=0,testing=false,confirmOrder=null,clock=()=>Date.now()}){
 const cipher=protect(dataKey),digest=value=>crypto.createHmac('sha256',sessionKey).update(value).digest('hex');
 const emailKey=value=>{const email=adminEmail(value);if(!email)throw new ShopError(400,'이메일 주소를 확인해주세요.');return digest('email:'+email);};
 const find=async id=>(await db.query('SELECT * FROM shop_members WHERE id=? AND status=\'active\'',[id]))[0]||null;
 const profile=row=>({id:row.id,email_verified:false,...cipher.decrypt(row.profile_cipher),password_enabled:!!row.password_hash,created_at:row.created_at});
 const owner=id=>hash('member:'+id);
 const check=()=>{if(!enabled)throw new ShopError(503,'회원 서비스를 준비하고 있습니다.');};
 const pass=async value=>{if(typeof value!=='string'||value.length<12||value.length>128||!value.trim())throw new ShopError(400,'비밀번호는 12~128자로 입력해주세요.');const salt=random();return salt+':'+(await scrypt(value,salt,64)).toString('hex');};
 async function balance(id){return (await db.query('SELECT COALESCE(SUM(amount),0) AS balance FROM shop_points WHERE member_id=?',[id]))[0].balance;}
 async function issue(row){const token=random(),now=clock();const result=await db.batch([{sql:'DELETE FROM shop_member_sessions WHERE expires_at<=? OR member_id IN (SELECT id FROM shop_members WHERE status<>\'active\')',params:[now]},{sql:'INSERT INTO shop_member_sessions(token_hash,member_id,expires_at,created_at) SELECT ?,id,?,? FROM shop_members WHERE id=? AND status=\'active\' AND password_hash=? RETURNING token_hash',params:[digest('session:'+token),now+7*86400000,now,row.id,row.password_hash]},{sql:'INSERT INTO shop_member_activity(member_id,last_login_at,login_count) SELECT id,?,1 FROM shop_members WHERE id=? AND status=\'active\' AND password_hash=? ON CONFLICT(member_id) DO UPDATE SET last_login_at=excluded.last_login_at,login_count=shop_member_activity.login_count+1',params:[now,row.id,row.password_hash]}]);if(!result[1].length)throw new ShopError(401,'계정 정보가 변경됐습니다. 다시 로그인해주세요.');return {member:profile(row),token};}
 async function authenticate(token){if(!enabled||typeof token!=='string'||!/^[a-zA-Z0-9_-]{43}$/.test(token))return null;const row=(await db.query('SELECT m.*,s.created_at AS authenticated_at FROM shop_member_sessions s JOIN shop_members m ON m.id=s.member_id WHERE s.token_hash=? AND s.expires_at>? AND m.status=\'active\'',[digest('session:'+token),clock()]))[0];return row?{...profile(row),authenticated_at:row.authenticated_at,owner:owner(row.id)}:null;}
 const socialKey=(provider,subjectHash)=>{if(!['kakao','google','naver'].includes(provider)||!/^[a-f0-9]{64}$/.test(subjectHash||''))throw new ShopError(400,'간편로그인 정보를 확인해주세요.');return 'social:'+digest(provider+':'+subjectHash);};
 async function socialRow(provider,subjectHash){socialKey(provider,subjectHash);return(await db.query("SELECT m.* FROM shop_social_identities i JOIN shop_members m ON m.id=i.member_id WHERE i.provider=? AND i.subject_hash=? AND m.status='active'",[provider,subjectHash]))[0]||null;}
 function policy(){return {earn_enabled:earnBasisPoints>0,earn_basis_points:earnBasisPoints,redemption_enabled:false,version:VERSION,testing};}
 return {enabled,authenticate,owner,policy,
  async socialLogin(provider,subjectHash){check();const row=await socialRow(provider,subjectHash);return row?issue(row):null;},
  async socialSignup(identity,input){check();const emailHash=socialKey(identity.provider,identity.subject_hash);if(input.terms!==true||input.privacy!==true||input.age14!==true)throw new ShopError(400,'만 14세 이상 확인과 필수 약관에 동의해주세요.');const name=typeof input.name==='string'?input.name.trim():'';if(name.length<2||name.length>60||/[\x00-\x1f\x7f]/.test(name))throw new ShopError(400,'이름은 2~60자로 입력해주세요.');
   const id='NM-'+crypto.randomUUID(),now=clock(),email=adminEmail(identity.email)||'',data=cipher.encrypt({name,email,email_verified:!!email&&identity.email_verified===true});
   await db.batch([{sql:"INSERT INTO shop_members(id,email_hash,owner_hash,profile_cipher,password_hash,recovery_hash,terms_version,consented_at,created_at,status) SELECT ?,?,?,?,'','',?,?,?,'active' WHERE NOT EXISTS(SELECT 1 FROM shop_social_identities WHERE provider=? AND subject_hash=?) ON CONFLICT(email_hash) DO NOTHING",params:[id,emailHash,owner(id),data,VERSION,now,now,identity.provider,identity.subject_hash]},{sql:"INSERT INTO shop_social_identities(provider,subject_hash,member_id,created_at) SELECT ?,?,id,? FROM shop_members WHERE id=? AND status='active' ON CONFLICT DO NOTHING",params:[identity.provider,identity.subject_hash,now,id]}]);
   const row=await socialRow(identity.provider,identity.subject_hash);if(!row)throw new ShopError(409,'가입 정보를 다시 확인해주세요.');return {...await issue(row),created:row.id===id};
  },
  async socialLink(member,provider,subjectHash){check();socialKey(provider,subjectHash);if(!member||member.authenticated_at<clock()-600000)throw new ShopError(401,'계정 연결 전 다시 로그인해주세요.');const row=await find(member.id);if(!row)throw new ShopError(401,'다시 로그인해주세요.');await db.query("INSERT INTO shop_social_identities(provider,subject_hash,member_id,created_at) SELECT ?,?,id,? FROM shop_members WHERE id=? AND status='active' AND password_hash=? ON CONFLICT DO NOTHING",[provider,subjectHash,clock(),row.id,row.password_hash]);const linked=await socialRow(provider,subjectHash);if(!linked||linked.id!==member.id)throw new ShopError(409,'이미 다른 회원 계정에 연결되어 있거나 다른 계정이 연결된 서비스입니다.');return {linked:true};},
  async signup(input){check();if(input.terms!==true||input.privacy!==true||input.age14!==true)throw new ShopError(400,'만 14세 이상 확인과 필수 약관에 동의해주세요.');
   const email=adminEmail(input.email),emailHash=emailKey(input.email),name=typeof input.name==='string'?input.name.trim():'';
   if(name.length<2||name.length>60||/[\x00-\x1f\x7f]/.test(name))throw new ShopError(400,'이름은 2~60자로 입력해주세요.');
   const password=await pass(input.password),id='NM-'+crypto.randomUUID(),recovery=random(),now=clock();
   const row={id,email_hash:emailHash,owner_hash:owner(id),profile_cipher:cipher.encrypt({email,name}),password_hash:password,recovery_hash:digest('recovery:'+recovery),created_at:now};
   await db.query('INSERT INTO shop_members(id,email_hash,owner_hash,profile_cipher,password_hash,recovery_hash,terms_version,consented_at,created_at,status) VALUES(?,?,?,?,?,?,?,?,?,\'active\') ON CONFLICT(email_hash) DO NOTHING',[id,emailHash,row.owner_hash,row.profile_cipher,password,row.recovery_hash,VERSION,now,now]);
   if(!(await find(id)))throw new ShopError(409,'가입 정보를 확인해주세요. 이미 가입했다면 로그인 또는 계정 복구를 이용해주세요.');
   return {...await issue(row),recovery_code:recovery};
  },
  async login(input){check();const key=emailKey(input.email),row=(await db.query('SELECT * FROM shop_members WHERE email_hash=? AND status=\'active\'',[key]))[0];
   const matched=await passwordMatches(input.password,row?.password_hash||'membership-dummy-salt:'+('0'.repeat(128)));if(!row||!matched)throw new ShopError(401,'이메일 또는 비밀번호를 확인해주세요.');return issue(row);
  },
  async logout(token){if(token)await db.query('DELETE FROM shop_member_sessions WHERE token_hash=?',[digest('session:'+token)]);return {authenticated:false};},
  async me(member){if(!member)return {authenticated:false,enabled,policy:policy()};return {authenticated:true,member:{id:member.id,email:member.email,name:member.name,email_verified:member.email_verified,password_enabled:member.password_enabled,providers:(await db.query('SELECT provider FROM shop_social_identities WHERE member_id=? ORDER BY provider',[member.id])).map(i=>i.provider)},points:{balance:await balance(member.id),history:await db.query('SELECT amount,reason,kind,created_at FROM shop_points WHERE member_id=? ORDER BY created_at DESC,id DESC LIMIT 50',[member.id])},policy:policy()};},
  async delivery(member,{contactOnly=false}={}){
   if(!member)throw new ShopError(401,'로그인 후 회원정보와 최근 배송지를 선택할 수 있습니다.');check();
   const row=await find(member.id);if(!row)throw new ShopError(401,'다시 로그인해주세요.');
   const saved=deliveryContact(cipher.decrypt(row.profile_cipher),contactOnly),recent=[],seen=new Set();
   // Derive ownership from the authenticated member ID, never a query parameter,
   // email match, guest cookie or caller-supplied owner hash. No new PII store.
   const orders=await db.query("SELECT customer_cipher FROM shop_orders WHERE customer_hash=? AND state<>'CANCELED' ORDER BY created_at DESC,id DESC LIMIT 50",[owner(row.id)]);
   for(const order of orders){
    let customer;try{customer=cipher.decrypt(order.customer_cipher);}catch{continue;}
    const address=deliveryContact(customer,contactOnly);if(Object.values(address).some(v=>!v))continue;
    const key=JSON.stringify({...address,phone:address.phone.replace(/[ -]/g,'')});if(seen.has(key))continue;seen.add(key);recent.push(address);if(recent.length===10)break;
   }
   return {authenticated:true,profile:saved,recent};
  },
  async changePassword(member,input){if(!member)throw new ShopError(401,'로그인이 필요합니다.');const row=await find(member.id);if(!await passwordMatches(input.current_password,row?.password_hash))throw new ShopError(401,'현재 비밀번호를 확인해주세요.');const password=await pass(input.password),recovery=random();
   const result=await db.batch([{sql:'UPDATE shop_members SET password_hash=?,recovery_hash=? WHERE id=? AND password_hash=? RETURNING id',params:[password,digest('recovery:'+recovery),row.id,row.password_hash]},{sql:'DELETE FROM shop_member_sessions WHERE member_id=? AND EXISTS(SELECT 1 FROM shop_members WHERE id=? AND password_hash=?)',params:[row.id,row.id,password]}]);if(!result[0].length)throw new ShopError(409,'계정 정보가 변경됐습니다. 다시 로그인해주세요.');return {changed:true,recovery_code:recovery};
  },
  async recover(input){check();const key=emailKey(input.email),code=typeof input.recovery_code==='string'?input.recovery_code:'';if(!/^[a-zA-Z0-9_-]{43}$/.test(code))throw new ShopError(400,'가입할 때 저장한 복구 코드를 확인해주세요.');const password=await pass(input.password),recovery=random(),old=digest('recovery:'+code);
   const rows=await db.batch([{sql:'UPDATE shop_members SET password_hash=?,recovery_hash=? WHERE email_hash=? AND recovery_hash=? AND status=\'active\' RETURNING id',params:[password,digest('recovery:'+recovery),key,old]},{sql:'DELETE FROM shop_member_sessions WHERE member_id IN (SELECT id FROM shop_members WHERE email_hash=? AND recovery_hash=?)',params:[key,digest('recovery:'+recovery)]}]);if(!rows[0].length)throw new ShopError(401,'이메일 또는 복구 코드를 확인해주세요.');return {changed:true,recovery_code:recovery};
  },
  async close(member,input){if(!member)throw new ShopError(401,'로그인이 필요합니다.');const row=await find(member.id);const verified=row?.password_hash?await passwordMatches(input.password,row.password_hash):row&&member.authenticated_at>=clock()-600000;if(input.confirmed!==true||!verified)throw new ShopError(400,row?.password_hash?'비밀번호와 탈퇴 동의를 확인해주세요.':'간편로그인으로 다시 로그인한 후 10분 이내에 탈퇴 동의를 확인해주세요.');
   if((await db.query("SELECT id FROM shop_orders WHERE customer_hash=? AND state NOT IN ('CANCELED','PAID') LIMIT 1",[member.owner])).length)throw new ShopError(409,'진행 중인 주문이 있습니다. 고객센터에서 주문 처리 후 탈퇴해주세요.');
   const erased=cipher.encrypt({name:'탈퇴 회원',email:''}),marker='closed:'+random();const result=await db.batch([{sql:"UPDATE shop_members SET status='closed',email_hash=?,profile_cipher=?,password_hash='',recovery_hash='',closed_at=? WHERE id=? AND status='active' AND password_hash=? RETURNING id",params:[marker,erased,clock(),row.id,row.password_hash]},{sql:"DELETE FROM shop_member_sessions WHERE member_id=? AND EXISTS(SELECT 1 FROM shop_members WHERE id=? AND status='closed')",params:[row.id,row.id]},{sql:"DELETE FROM shop_social_identities WHERE member_id=? AND EXISTS(SELECT 1 FROM shop_members WHERE id=? AND status='closed')",params:[row.id,row.id]},{sql:"DELETE FROM shop_member_crm WHERE member_id=? AND EXISTS(SELECT 1 FROM shop_members WHERE id=? AND status='closed')",params:[row.id,row.id]},{sql:"DELETE FROM shop_member_activity WHERE member_id=? AND EXISTS(SELECT 1 FROM shop_members WHERE id=? AND status='closed')",params:[row.id,row.id]}]);if(!result[0].length)throw new ShopError(409,'계정 정보가 변경됐습니다. 다시 확인해주세요.');return {closed:true};
  },
  async adminList(){check();const rows=await db.query("SELECT m.*,COALESCE((SELECT SUM(amount) FROM shop_points p WHERE p.member_id=m.id),0) AS balance FROM shop_members m WHERE status='active' ORDER BY created_at DESC LIMIT 100");return {members:rows.map(row=>({...profile(row),balance:row.balance})),policy:policy()};},
  async adjust(input,actor){check();if(!/^NM-[a-f0-9-]{36}$/.test(input.id||'')||!Number.isSafeInteger(input.amount)||input.amount===0||Math.abs(input.amount)>1000000||typeof input.reason!=='string'||input.reason.trim().length<2||input.reason.length>200||!/^[-a-zA-Z0-9_]{16,80}$/.test(input.request_key||''))throw new ShopError(400,'회원과 적립금·조정 사유를 확인해주세요.');
   const reason=input.reason.trim(),fingerprint=hash(JSON.stringify([input.id,input.amount,reason])),key='manual:'+input.request_key;
   await db.query("INSERT INTO shop_points(id,member_id,amount,reason,kind,request_key,fingerprint,actor,created_at) SELECT ?,?,?,?,?,?,?,?,? FROM shop_members WHERE id=? AND status='active' AND (? > 0 OR COALESCE((SELECT SUM(amount) FROM shop_points WHERE member_id=?),0)>=-?) ON CONFLICT(request_key) DO NOTHING",[crypto.randomUUID(),input.id,input.amount,reason,'adjustment',key,fingerprint,actor,clock(),input.id,input.amount,input.id,input.amount]);
   const saved=(await db.query('SELECT fingerprint FROM shop_points WHERE request_key=?',[key]))[0];if(!saved||saved.fingerprint!==fingerprint)throw new ShopError(409,'잔액 또는 요청 정보를 확인해주세요.');return {saved:true,balance:await balance(input.id)};
  },
  async confirm(member,input){if(!member)throw new ShopError(401,'로그인이 필요합니다.');if(!earnBasisPoints)throw new ShopError(409,'적립 기준을 준비하고 있습니다.');if(!confirmOrder)throw new ShopError(503,'구매확정 연결을 확인해주세요.');await confirmOrder(input.id,member.owner,{confirmed:true});const row=await repo.get(input.id);if(!row||row.customer_hash!==member.owner)throw new ShopError(404,'주문을 찾을 수 없습니다.');const customer=cipher.decrypt(row.customer_cipher);
   if(row.state!=='PAID'||row.payment_mode!==(testing?'test':'live')||customer.rental||row.fulfillment!=='shipped'||(customer._admin_cases||[]).some(c=>!['closed','rejected'].includes(c.status)))throw new ShopError(409,'배송 완료 및 반품·교환 상태를 확인해주세요.');
   const shipments=customer._admin_shipments||[],originals=shipments.filter(s=>s.purpose==='original');if(!originals.length||originals.some(s=>!s.delivered_at))throw new ShopError(409,'배송 완료 확인 후 구매확정할 수 있습니다.');
   const amount=Math.floor(Math.max(0,Math.min(row.subtotal,row.total-row.shipping))*earnBasisPoints/10000);if(!Number.isSafeInteger(amount)||amount<1)throw new ShopError(409,'적립 대상 금액이 없습니다.');
   await db.query("INSERT INTO shop_points(id,member_id,amount,reason,kind,request_key,fingerprint,actor,source_order,created_at) SELECT ?,?,?,?,'purchase',?,?,?,id,? FROM shop_orders WHERE id=? AND version=? AND state='PAID' ON CONFLICT(request_key) DO NOTHING",[crypto.randomUUID(),member.id,amount,'상품 구매확정 적립','earn:'+row.id,hash(row.id),'customer',clock(),row.id,row.version]);if(!(await db.query('SELECT id FROM shop_points WHERE request_key=? AND member_id=?',['earn:'+row.id,member.id])).length)throw new ShopError(409,'주문 상태가 변경되어 적립을 다시 확인해야 합니다.');return {confirmed:true,balance:await balance(member.id)};
  }
 };
}
module.exports={memberService};
