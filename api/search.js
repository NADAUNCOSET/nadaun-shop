const fs=require('node:fs');
const path=require('node:path');
const gift=require('../server/gift-catalog.cjs');
const search=require('../server/shop-search.cjs');
const template=fs.readFileSync(path.join(process.cwd(),'search.html'),'utf8');
const promotionHandler=require('../server/promotions.cjs').createHandler({catalog:search.catalog,
 template:fs.readFileSync(path.join(process.cwd(),'promotions.html'),'utf8')});
const catalogHandler=require('../server/catalog-pages.cjs').createHandler({catalog:search.catalog,
 template:fs.readFileSync(path.join(process.cwd(),'catalog.html'),'utf8')});
module.exports=function(req,res){
 const url=new URL(req.url,'https://shop.nadaun.co');
 if(url.pathname==='/promotions.html'||url.searchParams.get('view')==='promotions'||req.query?.view==='promotions')return promotionHandler(req,res);
 if(['/catalog.html','/catalog_category.html'].includes(url.pathname)||/^\/brands\/[a-z0-9-]+\.html$/.test(url.pathname)||url.searchParams.get('view')==='catalog'||req.query?.view==='catalog')return catalogHandler(req,res);
 if(!['GET','HEAD'].includes(req.method)){res.setHeader('Allow','GET, HEAD');return res.status(405).end();}
 const result=search.render(new URL(req.url,'https://shop.nadaun.co').searchParams);
 res.setHeader('Content-Type','text/html; charset=utf-8');res.setHeader('X-Robots-Tag','noindex');res.setHeader('Cache-Control','public, max-age=0, s-maxage=60');
 return res.status(result.status).end(req.method==='HEAD'?'':gift.page(template,result));
};
