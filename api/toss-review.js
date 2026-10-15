'use strict';
const fs=require('node:fs');
const path=require('node:path');
const {reviewEndpoint}=require('../server/commerce/toss-review.cjs');
let handler;
module.exports=async function(req,res){
 try{
  if(!handler)handler=reviewEndpoint({env:process.env,catalog:JSON.parse(fs.readFileSync(path.join(process.cwd(),'data/catalog/catalog.json'),'utf8'))});
  return await handler(req,res);
 }catch{res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex,nofollow');return res.status(503).json({error:'테스트 결제 연결을 확인하고 있습니다.'});}
};
