const fs=require('node:fs');
const path=require('node:path');
const gift=require('../server/gift-catalog.cjs');
const search=require('../server/shop-search.cjs');
const template=fs.readFileSync(path.join(process.cwd(),'search.html'),'utf8');
module.exports=function(req,res){
 if(!['GET','HEAD'].includes(req.method)){res.setHeader('Allow','GET, HEAD');return res.status(405).end();}
 const result=search.render(new URL(req.url,'https://shop.nadaun.co').searchParams);
 res.setHeader('Content-Type','text/html; charset=utf-8');res.setHeader('X-Robots-Tag','noindex');res.setHeader('Cache-Control','public, max-age=0, s-maxage=60');
 return res.status(result.status).end(req.method==='HEAD'?'':gift.page(template,result));
};
