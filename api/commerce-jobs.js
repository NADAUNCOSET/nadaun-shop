const crypto=require('node:crypto');
const {runtime}=require('../server/commerce/runtime.cjs');
const {webhookEndpoint}=require('../server/commerce/payment-webhook.cjs');
const paymentWebhook=webhookEndpoint(()=>runtime());
module.exports=async(req,res)=>{
 if(req.query?.action==='toss-webhook')return paymentWebhook(req,res);
 res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex');
 const secret=process.env.SHOP_JOBS_SECRET,actual=String(req.headers.authorization||'');
 const expected='Bearer '+secret;
 if(req.method!=='POST'||!secret||secret.length<32||Buffer.byteLength(actual)!==Buffer.byteLength(expected)||!crypto.timingSafeEqual(Buffer.from(actual),Buffer.from(expected)))return res.status(401).json({error:'Unauthorized'});
 if(process.env.SHOP_ORDERS_ENABLED!=='true')return res.status(200).json({state:'disabled',processed:0});
 try{const current=runtime(),payments=await current.service.paymentDrain(),documents=await current.documents.drain(1),shipping=await current.service.labelDrain();return res.status(200).json({...documents,shipping,payments});}catch{return res.status(503).json({error:'Order processing pending'});}
};
