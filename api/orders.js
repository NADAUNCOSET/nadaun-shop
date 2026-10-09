const {runtime}=require('../server/commerce/runtime.cjs');
const {endpoint}=require('../server/commerce/http.cjs');
let handler;
module.exports=async function(req,res){
 if(!handler){
  try{
   const {repo,service,admin}=runtime();
   handler=endpoint({service,repo,adminService:admin,enabled:process.env.SHOP_ORDERS_ENABLED==='true',rentalEnabled:process.env.SHOP_RENTAL_REQUESTS_ENABLED==='true',sessionKey:process.env.SHOP_SESSION_KEY,password:process.env.SHOP_ADMIN_PASSWORD_HASH});
  }catch{
   res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex');
   if(req.method==='GET'&&new URL(req.url,'https://shop.nadaun.co').searchParams.get('action')==='config')return res.status(200).json({ordersEnabled:false,rentalRequestsEnabled:false,adminEnabled:false,paymentProvider:'inicis'});
   return res.status(503).json({error:'주문 서비스 연결을 준비 중입니다.'});
  }
 }
 return handler(req,res);
};
