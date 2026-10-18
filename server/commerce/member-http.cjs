'use strict';
const {ShopError,hash,sessions,adminEmail}=require('./security.cjs');
const {cookieValue}=require('./test-context.cjs');
function memberEndpoint({members,repo,crm=null,sessionKey,adminPasswordEmail='',cookiePrefix='nadaun',testing=false}){
 const tokenName='__Host-'+cookiePrefix+'-member',signed=sessions(sessionKey),email=adminPasswordEmail?adminEmail(adminPasswordEmail):null;
 const cookie=(token,seconds)=>tokenName+'='+token+'; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age='+seconds;
 return async(req,res)=>{
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex, nofollow');
  try{const url=new URL(req.url,'https://shop.nadaun.co'),action=url.searchParams.get('action')||'me';if(!['POST','GET'].includes(req.method))throw new ShopError(405,'요청 방식을 확인해주세요.');
   const adminAction=action.startsWith('admin-'),origins=adminAction?['https://shop.nadaun.co','https://order.nadaun.co']:['https://shop.nadaun.co'];
   if(req.method==='POST'&&!origins.includes(req.headers.origin))throw new ShopError(403,'사이트에서 다시 요청해주세요.');
   const ip=String(req.headers['x-forwarded-for']||'unknown').split(',')[0].trim();await repo.limit('member-api:'+hash(sessionKey+ip),120,60);
   let input=req.body;if(req.method==='POST'){if(typeof input==='string'){if(Buffer.byteLength(input)>8192)throw new ShopError(413,'입력 내용을 확인해주세요.');try{input=JSON.parse(input);}catch{throw new ShopError(400,'입력 형식을 확인해주세요.');}}if(!input||typeof input!=='object'||Array.isArray(input)||Buffer.byteLength(JSON.stringify(input))>8192)throw new ShopError(400,'입력 내용을 확인해주세요.');}
   const token=cookieValue(req,tokenName),member=await members.authenticate(token);
   if(action==='me'&&req.method==='GET')return res.status(200).json({...await members.me(member),testing});
   if(adminAction){const admin=signed.read(cookieValue(req,'__Host-'+cookiePrefix+'-admin'),'admin');if(!admin||email&&admin!==email)throw new ShopError(401,'관리자 로그인이 필요합니다.');
    if(crm){
     if(action==='admin-overview'&&req.method==='GET')return res.status(200).json(await crm.overview());
     if(action==='admin-customers'&&req.method==='POST')return res.status(200).json(await crm.list(input));
     if(action==='admin-customer'&&req.method==='GET')return res.status(200).json(await crm.detail(url.searchParams.get('id')));
     if(action==='admin-customer-note'&&req.method==='POST')return res.status(200).json(await crm.saveNote(input,admin));
     if(action==='admin-campaigns'&&req.method==='GET')return res.status(200).json(await crm.campaigns());
     if(action==='admin-campaign-save'&&req.method==='POST')return res.status(200).json(await crm.saveCampaign(input,admin));
    }
    if(action==='admin-members'&&req.method==='GET')return res.status(200).json(await members.adminList());
    if(action==='admin-points'&&req.method==='POST')return res.status(200).json(await members.adjust(input,admin));
   }
   if(req.method==='POST'){
    if(['signup','login','recover'].includes(action)){await repo.limit('member-auth:'+hash(sessionKey+ip),15,900);if(input.email)await repo.limit('member-email:'+hash(sessionKey+String(input.email).trim().toLowerCase()),15,900);}
    if(action==='signup'||action==='login'){const value=await members[action](input);res.setHeader('Set-Cookie',cookie(value.token,7*86400));delete value.token;return res.status(action==='signup'?201:200).json(value);}
    if(action==='logout'){await members.logout(token);res.setHeader('Set-Cookie',cookie('',0));return res.status(200).json({authenticated:false});}
    if(action==='recover'){const result=await members.recover(input);res.setHeader('Set-Cookie',cookie('',0));return res.status(200).json(result);}
    if(action==='password'||action==='close'){const result=await members[action==='password'?'changePassword':'close'](member,input);res.setHeader('Set-Cookie',cookie('',0));return res.status(200).json(result);}
    if(action==='confirm')return res.status(200).json(await members.confirm(member,input));
   }
   throw new ShopError(404,'요청을 찾을 수 없습니다.');
  }catch(e){return res.status(e instanceof ShopError?e.status:503).json({error:e instanceof ShopError?e.message:'회원 정보를 확인하고 있습니다. 잠시 후 다시 시도해주세요.'});}
 };
}
module.exports={memberEndpoint};
