const crypto=require('node:crypto');
const {runtime}=require('../server/commerce/runtime.cjs');
module.exports=async(req,res)=>{
 res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex');
 const secret=process.env.SHOP_JOBS_SECRET,actual=String(req.headers.authorization||'');
 const expected='Bearer '+secret;
 if(req.method!=='POST'||!secret||secret.length<32||Buffer.byteLength(actual)!==Buffer.byteLength(expected)||!crypto.timingSafeEqual(Buffer.from(actual),Buffer.from(expected)))return res.status(401).json({error:'Unauthorized'});
 try{return res.status(200).json(await runtime().documents.drain(2));}catch{return res.status(503).json({error:'Document processing pending'});}
};
