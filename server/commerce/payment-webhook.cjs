'use strict';
const {ShopError,hash}=require('./security.cjs');
function webhookEndpoint(current){return async(req,res)=>{
 res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex');
 if(req.method!=='POST')return res.status(405).json({error:'Method not allowed'});
 try{
  if(Buffer.byteLength(typeof req.body==='string'?req.body:JSON.stringify(req.body||{}))>32768)return res.status(413).json({error:'Payload too large'});
  let body=req.body;try{if(typeof body==='string')body=JSON.parse(body);}catch{return res.status(400).json({error:'Invalid payload'});}
  const {service,repo}=current();await repo.limit('payment-webhook:'+hash(String(req.headers['x-forwarded-for']||'unknown')),60,60);
  return res.status(200).json(await service.paymentWebhook(body));
 }catch(e){return res.status(e instanceof ShopError?e.status:503).json({error:'Payment reconciliation pending'});}
};}
module.exports={webhookEndpoint};
