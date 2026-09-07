const fs=require('node:fs');
const path=require('node:path');
const {database}=require('../server/commerce/d1.cjs');
const {repository,orderService}=require('../server/commerce/orders.cjs');
const {toss}=require('../server/commerce/toss.cjs');
const {endpoint}=require('../server/commerce/http.cjs');
let handler;
module.exports=async function(req,res){
 if(!handler){
  try{
   if(process.env.SHOP_ORDERS_ENABLED!=='true')throw Error('disabled');
   const catalog=JSON.parse(fs.readFileSync(path.join(process.cwd(),'data/catalog/catalog.json'),'utf8'));
   const cache=new Map();
   function detail(p){if(!/^[a-f0-9]{2}$/.test(p.detail_bucket))throw Error('Invalid detail shard');if(!cache.has(p.detail_bucket))cache.set(p.detail_bucket,JSON.parse(fs.readFileSync(path.join(process.cwd(),'data/catalog/details',p.detail_bucket+'.json'),'utf8')));const d=cache.get(p.detail_bucket)[p.id];if(!d)throw Error('Missing detail');return d;}
   const repo=repository(database(process.env));let payment=null;
   if(process.env.SHOP_PAYMENT_MODE)payment=toss(process.env);
   if(!process.env.SHOP_ADMIN_PASSWORD_HASH)throw Error('admin not configured');
   handler=endpoint({service:orderService({repo,catalog,detail,dataKey:process.env.SHOP_ORDER_DATA_KEY,payment}),repo,sessionKey:process.env.SHOP_SESSION_KEY,password:process.env.SHOP_ADMIN_PASSWORD_HASH});
  }catch{
   res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex');
   if(req.method==='GET'&&new URL(req.url,'https://shop.nadaun.co').searchParams.get('action')==='config')return res.status(200).json({ordersEnabled:false});
   return res.status(503).json({error:'주문 서비스 연결을 준비 중입니다.'});
  }
 }
 return handler(req,res);
};
