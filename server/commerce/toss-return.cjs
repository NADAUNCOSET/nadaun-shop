'use strict';
function parseQuery(req){
 const url=new URL(req.url,'https://shop.nadaun.co'),keys=[...url.searchParams.keys()];
 if(url.search.length>4096||new Set(keys).size!==keys.length)throw Error('Invalid callback');
 return Object.fromEntries(url.searchParams);
}
function returnEndpoint(getService){
 return async(req,res)=>{
  res.setHeader('Cache-Control','no-store');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('X-Robots-Tag','noindex');
  if(req.method!=='GET'){res.setHeader('Allow','GET');return res.status(405).end();}
  let target='/orders.html?result=check';
  try{const order=await getService().acceptReturn(parseQuery(req));target='/orders.html?result=returned#'+encodeURIComponent(order.id);}catch{}
  res.setHeader('Location',target);return res.status(303).end();
 };
}
module.exports={parseQuery,returnEndpoint};
