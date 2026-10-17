'use strict';
const {database}=require('../server/commerce/d1.cjs');
const {repository}=require('../server/commerce/orders.cjs');
const {ShopError,hash,passwordMatches,sessions,identityMatches}=require('../server/commerce/security.cjs');
const {MODE_COOKIE,context}=require('../server/commerce/test-context.cjs');
module.exports=async(req,res)=>{
 res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex, nofollow');
 try{
  const env=process.env,configured=env.SHOP_QA_ENABLED==='true'&&/^test_ck_[\w-]+$/.test(env.SHOP_QA_TOSS_CLIENT_KEY||'')&&/^test_sk_[\w-]+$/.test(env.SHOP_QA_TOSS_SECRET_KEY||'');
  if(req.method==='GET')return res.status(200).json({configured,testing:context(req,env).testing,key_source:'official_documentation_demo',real_charge:false});
  if(req.method!=='POST')throw new ShopError(405,'요청 방식을 확인해주세요.');
  if(!['https://shop.nadaun.co','https://order.nadaun.co'].includes(req.headers.origin))throw new ShopError(403,'사이트에서 다시 요청해주세요.');
  let body=req.body;if(typeof body==='string'){if(Buffer.byteLength(body)>2048)throw new ShopError(413,'입력 내용을 확인해주세요.');try{body=JSON.parse(body);}catch{throw new ShopError(400,'입력 내용을 확인해주세요.');}}
  if(!body||typeof body!=='object'||Array.isArray(body)||Buffer.byteLength(JSON.stringify(body))>2048)throw new ShopError(400,'입력 내용을 확인해주세요.');
  if(body.action==='exit'){res.setHeader('Set-Cookie',MODE_COOKIE+'=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0');return res.status(200).json({testing:false});}
  if(!configured)throw new ShopError(503,'테스트 연결을 준비하고 있습니다.');
  const repo=repository(database(env));await repo.limit('qa-login:'+hash(env.SHOP_SESSION_KEY+String(req.headers['x-forwarded-for']||'unknown')),10,900);
  const valid=await passwordMatches(body.password,env.SHOP_ADMIN_PASSWORD_HASH);if(!valid||env.SHOP_ADMIN_EMAIL&&!identityMatches(body.email,env.SHOP_ADMIN_EMAIL))throw new ShopError(401,'관리자 로그인 정보를 확인해주세요.');
  // Verify the isolated schema exists before issuing the test-session cookie.
  await database({...env,SHOP_TEST_CONTEXT:'true'}).query('SELECT COUNT(*) AS n FROM shop_members');
  const token=sessions(env.SHOP_SESSION_KEY).issue('storefront-qa','storefront-qa',4*3600);
  res.setHeader('Set-Cookie',MODE_COOKIE+'='+token+'; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=14400');return res.status(200).json({testing:true});
 }catch(e){return res.status(e instanceof ShopError?e.status:503).json({error:e instanceof ShopError?e.message:'테스트 환경을 확인하고 있습니다.'});}
};
