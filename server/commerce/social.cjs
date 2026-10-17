'use strict';
const crypto=require('node:crypto');
const {ShopError,protect,random}=require('./security.cjs');
const {socialProviders}=require('./social-providers.cjs');
const validToken=value=>typeof value==='string'&&/^[a-zA-Z0-9_-]{43}$/.test(value);
function socialService({db,members,dataKey,sessionKey,env,fetcher=fetch,clock=()=>Date.now()}){
 const cipher=protect(dataKey),providers=socialProviders(env,fetcher),digest=value=>crypto.createHmac('sha256',sessionKey).update(value).digest('hex');
 const recent=member=>member&&member.authenticated_at>=clock()-600000;
 async function cleanup(){await db.batch([{sql:'DELETE FROM shop_oauth_attempts WHERE expires_at<=?',params:[clock()]},{sql:'DELETE FROM shop_social_enrollments WHERE expires_at<=?',params:[clock()]}]);}
 async function pending(ticket){if(!validToken(ticket))return null;const row=(await db.query('SELECT private_cipher FROM shop_social_enrollments WHERE ticket_hash=? AND expires_at>?',[digest('enroll:'+ticket),clock()]))[0];return row?cipher.decrypt(row.private_cipher):null;}
 return {
  status:()=>providers.status(),
  async start(provider,{mode='login',member=null,memberToken='',useSdk=false}={}){
   if(!['login','link'].includes(mode))throw new ShopError(400,'로그인 요청을 확인해주세요.');if(mode==='login'&&member)throw new ShopError(409,'마이페이지의 로그인 방식 연결을 이용해주세요.');if(mode==='link'&&!recent(member))throw new ShopError(401,'계정 연결 전 다시 로그인해주세요.');
   const state=random(),binding=random(),verifier=random(),value=providers.authorize(provider,{state,verifier,useSdk});await cleanup();
   await db.query('INSERT INTO shop_oauth_attempts(state_hash,provider,binding_hash,private_cipher,expires_at,created_at) VALUES(?,?,?,?,?,?)',[digest('state:'+state),provider,digest('bind:'+binding),cipher.encrypt({verifier:value.uses_pkce?verifier:'',mode,member_id:mode==='link'?member.id:null,session_hash:mode==='link'?digest('link:'+memberToken):null}),clock()+600000,clock()]);
   return {...value,state,binding};
  },
  async callback(provider,{state,code,error,binding,member=null,memberToken=''}){
   if(!validToken(state)||!validToken(binding))throw new ShopError(400,'로그인 요청이 만료됐습니다. 다시 시작해주세요.');
   const rows=await db.query('DELETE FROM shop_oauth_attempts WHERE state_hash=? AND provider=? AND binding_hash=? AND expires_at>? RETURNING private_cipher',[digest('state:'+state),provider,digest('bind:'+binding),clock()]);if(!rows.length)throw new ShopError(400,'로그인 요청이 만료됐습니다. 다시 시작해주세요.');
   if(error)throw new ShopError(400,'간편로그인이 취소되었습니다.');if(typeof code!=='string'||code.length<1||code.length>4096||/[\x00-\x20\x7f]/.test(code))throw new ShopError(400,'로그인 인증을 확인해주세요.');
   const attempt=cipher.decrypt(rows[0].private_cipher);if(attempt.mode==='link'&&(!recent(member)||member.id!==attempt.member_id||digest('link:'+memberToken)!==attempt.session_hash))throw new ShopError(401,'계정 연결 전 다시 로그인해주세요.');
   const identity=await providers.exchange(provider,{code,state,verifier:attempt.verifier});identity.subject_hash=digest('subject:'+provider+':'+identity.subject);delete identity.subject;
   if(attempt.mode==='link')return members.socialLink(member,provider,identity.subject_hash);
   const login=await members.socialLogin(provider,identity.subject_hash);if(login)return login;
   const ticket=random();await cleanup();await db.query('INSERT INTO shop_social_enrollments(ticket_hash,private_cipher,expires_at,created_at) VALUES(?,?,?,?)',[digest('enroll:'+ticket),cipher.encrypt(identity),clock()+600000,clock()]);return {enrollment:true,ticket};
  },
  async pending(ticket){const value=await pending(ticket);return value?{provider:value.provider,name:value.name,email:value.email}:null;},
  async complete(ticket,input){const value=await pending(ticket);if(!value)throw new ShopError(400,'가입 확인 시간이 지났습니다. 간편로그인을 다시 시작해주세요.');
   // Validate before consuming; consume atomically before creating a member.
   if(input.terms!==true||input.privacy!==true||input.age14!==true||typeof input.name!=='string'||input.name.trim().length<2||input.name.length>60||/[\x00-\x1f\x7f]/.test(input.name))throw new ShopError(400,'이름과 만 14세 이상·필수 약관 동의를 확인해주세요.');
   const rows=await db.query('DELETE FROM shop_social_enrollments WHERE ticket_hash=? AND expires_at>? RETURNING private_cipher',[digest('enroll:'+ticket),clock()]);if(!rows.length)throw new ShopError(409,'가입 확인 시간이 지났습니다. 다시 로그인해주세요.');return members.socialSignup(cipher.decrypt(rows[0].private_cipher),input);
  },
  async cancel(ticket){if(validToken(ticket))await db.query('DELETE FROM shop_social_enrollments WHERE ticket_hash=?',[digest('enroll:'+ticket)]);return {canceled:true};}
 };
}
module.exports={socialService};
