'use strict';
const {ShopError,hash}=require('./security.cjs');
const {cookieValue}=require('./test-context.cjs');
const {ORIGIN,PROVIDERS}=require('./social-providers.cjs');
function socialEndpoint({social,members,repo,sessionKey,cookiePrefix='nadaun',testing=false}){
 const name=key=>'__Host-'+cookiePrefix+'-'+key,cookie=(key,value,seconds)=>name(key)+'='+value+'; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age='+seconds;
 return async(req,res)=>{
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex, nofollow');res.setHeader('Referrer-Policy','no-referrer');let callback=false,provider;
  const redirect=marker=>{res.setHeader('Location',ORIGIN+'/account.html?social='+marker);return res.status(303).end();};
  try{const url=new URL(req.url,ORIGIN),match=url.pathname.match(/^\/auth\/(kakao|google|naver)\/callback$/);callback=!!match||url.pathname==='/api/member-oauth'&&url.searchParams.get('action')==='callback';
   for(const key of ['action','provider','state','code','error'])if(url.searchParams.getAll(key).length>1)throw new ShopError(400,'로그인 요청을 확인해주세요.');
   const action=callback?'callback':url.searchParams.get('action')||'status';provider=match?.[1]||url.searchParams.get('provider');if(provider&&!Object.hasOwn(PROVIDERS,provider))throw new ShopError(400,'로그인 서비스를 확인해주세요.');
   const ip=String(req.headers['x-forwarded-for']||'unknown').split(',')[0].trim();await repo.limit('social-api:'+hash(sessionKey+ip),90,60);
   const memberToken=cookieValue(req,name('member')),member=await members.authenticate(memberToken),ticket=cookieValue(req,name('social-pending'));
   if(req.method==='GET'&&action==='status')return res.status(200).json({providers:social.status(),pending:await social.pending(ticket),testing});
   if(req.method==='GET'&&action==='callback'&&callback){const result=await social.callback(provider,{state:url.searchParams.get('state'),code:url.searchParams.get('code'),error:url.searchParams.get('error'),binding:cookieValue(req,name('oauth-'+provider)),member,memberToken});const cookies=[cookie('oauth-'+provider,'',0),cookie('social-pending','',0)];
    if(result.token){cookies.push(cookie('member',result.token,7*86400));await social.cancel(ticket);}if(result.ticket){await social.cancel(ticket);cookies.push(cookie('social-pending',result.ticket,600));}res.setHeader('Set-Cookie',cookies);return redirect(result.linked?'linked':result.enrollment?'complete':'success');}
   if(req.method!=='POST')throw new ShopError(405,'요청 방식을 확인해주세요.');if(req.headers.origin!==ORIGIN)throw new ShopError(403,'사이트에서 다시 요청해주세요.');
   let input=req.body;if(typeof input==='string'){if(Buffer.byteLength(input)>4096)throw new ShopError(413,'입력 내용을 확인해주세요.');try{input=JSON.parse(input);}catch{throw new ShopError(400,'입력 내용을 확인해주세요.');}}if(!input||typeof input!=='object'||Array.isArray(input)||Buffer.byteLength(JSON.stringify(input))>4096)throw new ShopError(400,'입력 내용을 확인해주세요.');
   if(action==='start'){await repo.limit('social-start:'+hash(sessionKey+ip),20,900);const result=await social.start(provider,{mode:input.mode||'login',member,memberToken,useSdk:input.use_kakao_sdk===true});res.setHeader('Set-Cookie',cookie('oauth-'+provider,result.binding,600));delete result.binding;delete result.state;delete result.uses_pkce;return res.status(200).json(result);}
   if(action==='complete'){await repo.limit('social-complete:'+hash(sessionKey+ip),20,900);const result=await social.complete(ticket,input);res.setHeader('Set-Cookie',[cookie('member',result.token,7*86400),cookie('social-pending','',0)]);delete result.token;return res.status(201).json(result);}
   if(action==='cancel'){await social.cancel(ticket);res.setHeader('Set-Cookie',cookie('social-pending','',0));return res.status(200).json({canceled:true});}
   throw new ShopError(404,'요청을 찾을 수 없습니다.');
  }catch(e){if(callback){if(provider&&Object.hasOwn(PROVIDERS,provider))res.setHeader('Set-Cookie',cookie('oauth-'+provider,'',0));return redirect('error');}return res.status(e instanceof ShopError?e.status:503).json({error:e instanceof ShopError?e.message:'간편로그인을 확인하고 있습니다. 잠시 후 다시 시도해주세요.'});}
 };
}
module.exports={socialEndpoint};
