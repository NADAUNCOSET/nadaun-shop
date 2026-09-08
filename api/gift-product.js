const fs=require('node:fs');
const path=require('node:path');
const gift=require('../server/gift-catalog.cjs');
const template=fs.readFileSync(path.join(process.cwd(),'gift-item.html'),'utf8');
module.exports=function(req,res){
 if(!['GET','HEAD'].includes(req.method)){res.setHeader('Allow','GET, HEAD');return res.status(405).end();}
 const id=new URL(req.url,'https://shop.nadaun.co').searchParams.get('id');
 const result=gift.detail(id);
 res.setHeader('Content-Type','text/html; charset=utf-8');res.setHeader('Cache-Control','public, max-age=0, s-maxage=300');
 if(result.status!==200)res.setHeader('X-Robots-Tag','noindex');
 return res.status(result.status).end(req.method==='HEAD'?'':gift.page(template,result));
};
