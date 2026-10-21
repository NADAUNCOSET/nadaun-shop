const {runtime}=require('../server/commerce/runtime.cjs');
const {endpoint}=require('../server/commerce/http.cjs');
const {context}=require('../server/commerce/test-context.cjs');
const handlers=new Map();
module.exports=async function(req,res){
 let selected;try{selected=context(req);}catch{return res.status(503).json({error:'주문 연결을 확인해주세요.'});}
 const {env,cookiePrefix,testing}=selected,key=testing?'qa':'live';let handler=handlers.get(key);
 if(!handler){
  try{
   const {repo,service,admin,drafts,members,giftAdmin}=runtime(env);
   handler=endpoint({service,repo,adminService:admin,draftService:drafts||null,giftAdmin,members,cookiePrefix,testing,enabled:env.SHOP_ORDERS_ENABLED==='true',rentalEnabled:env.SHOP_RENTAL_REQUESTS_ENABLED==='true',giftEnabled:env.SHOP_GIFT_REQUESTS_ENABLED==='true',sessionKey:env.SHOP_SESSION_KEY,password:env.SHOP_ADMIN_PASSWORD_HASH,email:env.SHOP_ADMIN_EMAIL});handlers.set(key,handler);
  }catch{
   res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex');
   if(req.method==='GET'&&new URL(req.url,'https://shop.nadaun.co').searchParams.get('action')==='config')return res.status(200).json({ordersEnabled:false,rentalRequestsEnabled:false,giftRequestsEnabled:false,adminEnabled:false,adminLoginRequiresEmail:!!process.env.SHOP_ADMIN_EMAIL,paymentProvider:'toss'});
   return res.status(503).json({error:'주문 서비스 연결을 준비 중입니다.'});
  }
 }
 return handler(req,res);
};
