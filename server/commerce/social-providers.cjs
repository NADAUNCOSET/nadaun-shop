'use strict';
const crypto=require('node:crypto');
const {ShopError,adminEmail}=require('./security.cjs');
const PROVIDERS={
 kakao:{name:'카카오',authorize:'https://kauth.kakao.com/oauth/authorize',token:'https://kauth.kakao.com/oauth/token',userinfo:'https://kapi.kakao.com/v2/user/me'},
 google:{name:'Google',authorize:'https://accounts.google.com/o/oauth2/v2/auth',token:'https://oauth2.googleapis.com/token',userinfo:'https://openidconnect.googleapis.com/v1/userinfo'},
 naver:{name:'네이버',authorize:'https://nid.naver.com/oauth2.0/authorize',token:'https://nid.naver.com/oauth2.0/token',userinfo:'https://openapi.naver.com/v1/nid/me'}
};
const ORIGIN='https://shop.nadaun.co';
const redirectUri=provider=>ORIGIN+'/auth/'+provider+'/callback';
function socialProviders(env,fetcher=fetch){
 function config(provider){if(!Object.hasOwn(PROVIDERS,provider))throw new ShopError(400,'로그인 서비스를 확인해주세요.');const prefix='SHOP_OAUTH_'+provider.toUpperCase()+'_';return {...PROVIDERS[provider],id:env[prefix+'CLIENT_ID']||'',secret:env[prefix+'CLIENT_SECRET']||'',enabled:env.SHOP_MEMBERS_ENABLED==='true'&&env[prefix+'ENABLED']==='true',jsKey:provider==='kakao'?env[prefix+'JS_KEY']||'':''};}
 function ready(provider){const c=config(provider);return c.enabled&&!!c.id&&!!c.secret;}
 function requireReady(provider){const c=config(provider);if(!ready(provider))throw new ShopError(503,c.name+' 간편로그인을 준비하고 있습니다. 이메일 가입을 이용해주세요.');return c;}
 async function json(url,options){try{const r=await fetcher(url,{...options,redirect:'error',signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error();const data=await r.json();if(!data||typeof data!=='object'||Array.isArray(data)||data.error)throw Error();return data;}catch{throw new ShopError(502,'로그인 서비스의 인증을 확인하지 못했습니다. 다시 시도해주세요.');}}
 return {
  status:()=>Object.keys(PROVIDERS).map(id=>({id,name:PROVIDERS[id].name,ready:ready(id),kakao_talk:id==='kakao'&&ready(id)&&!!config(id).jsKey})),
  authorize(provider,{state,verifier,useSdk=false}){const c=requireReady(provider),sdk=provider==='kakao'&&!!c.jsKey&&useSdk,url=new URL(c.authorize);url.search=new URLSearchParams({response_type:'code',client_id:c.id,redirect_uri:redirectUri(provider),state}).toString();if(provider==='google'){url.searchParams.set('scope','openid profile email');url.searchParams.set('prompt','select_account');url.searchParams.set('access_type','online');}if(verifier&&provider!=='naver'&&!sdk){url.searchParams.set('code_challenge',crypto.createHash('sha256').update(verifier).digest('base64url'));url.searchParams.set('code_challenge_method','S256');}return {authorization_url:url.href,...(sdk?{sdk:{key:c.jsKey,redirect_uri:redirectUri(provider),state}}:{}),uses_pkce:provider!=='naver'&&!sdk};},
  async exchange(provider,{code,state,verifier}){const c=requireReady(provider),body=new URLSearchParams({grant_type:'authorization_code',client_id:c.id,client_secret:c.secret,redirect_uri:redirectUri(provider),code});if(provider==='naver')body.set('state',state);else if(verifier)body.set('code_verifier',verifier);
   const tokens=await json(c.token,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:body.toString()});if(typeof tokens.access_token!=='string'||tokens.access_token.length<1||tokens.access_token.length>8192||typeof tokens.token_type!=='string'||tokens.token_type.toLowerCase()!=='bearer')throw new ShopError(502,'로그인 인증을 확인해주세요.');
   const data=await json(c.userinfo,{method:'GET',headers:{Authorization:'Bearer '+tokens.access_token}});let subject,email,name,emailVerified=false;
   if(provider==='google'){subject=data.sub;email=data.email;name=data.name;emailVerified=data.email_verified===true;}
   if(provider==='naver'){if(data.resultcode!=='00')throw new ShopError(502,'네이버 회원 정보를 확인하지 못했습니다.');subject=data.response?.id;email=data.response?.email;name=data.response?.name;}
   if(provider==='kakao'){if(!Number.isSafeInteger(data.id)||data.id<=0)throw new ShopError(502,'카카오 회원 정보를 확인하지 못했습니다.');subject=String(data.id);email=data.kakao_account?.email;name=data.kakao_account?.profile?.nickname;emailVerified=data.kakao_account?.is_email_valid===true&&data.kakao_account?.is_email_verified===true;}
   if(typeof subject!=='string'||subject.length<1||subject.length>255||/[\x00-\x1f\x7f]/.test(subject))throw new ShopError(502,'로그인 계정을 확인하지 못했습니다.');
   return {provider,subject,email:adminEmail(email)||'',email_verified:emailVerified,name:typeof name==='string'?name.replace(/[\x00-\x1f\x7f]/g,'').slice(0,60):''};
  }
 };
}
module.exports={socialProviders,PROVIDERS,ORIGIN,redirectUri};
