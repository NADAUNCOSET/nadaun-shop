'use strict';
const crypto=require('node:crypto');
const {ShopError}=require('./security.cjs');
function parseBody(req){
 const type=String(req.headers['content-type']||'').split(';')[0].toLowerCase();
 if(type!=='application/x-www-form-urlencoded')throw new ShopError(415,'Unsupported callback format');
 let input=req.body;
 if(Buffer.isBuffer(input))input=input.toString('utf8');
 if(typeof input==='string'){
  if(Buffer.byteLength(input)>16384)throw new ShopError(413,'Callback too large');
  const params=new URLSearchParams(input),keys=[...params.keys()];
  if(new Set(keys).size!==keys.length)throw new ShopError(400,'Duplicate callback fields');
  input=Object.fromEntries(params);
 }
 if(!input||typeof input!=='object'||Array.isArray(input)||Buffer.byteLength(JSON.stringify(input))>16384||Object.values(input).some(v=>typeof v!=='string'))throw new ShopError(400,'Invalid callback');
 return input;
}
function returnEndpoint(getService){
 return async (req,res)=>{
  res.setHeader('Cache-Control','no-store');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('X-Robots-Tag','noindex');
  let target='/orders.html?result=check';
  if(req.method==='GET'&&new URL(req.url,'https://shop.nadaun.co').searchParams.get('action')==='close')target='/orders.html?result=closed';
  else if(req.method==='POST'){
   try{const order=await getService().acceptReturn(parseBody(req));target='/orders.html?result=returned#'+encodeURIComponent(order.id);}
   catch(error){if(error instanceof ShopError&&error.status<500){res.status(error.status);}}
  }else{res.setHeader('Allow','POST');return res.status(405).end();}
  // Provider POST callbacks cannot rely on SameSite=Lax customer cookies.
  // The service authenticates the signed, expiring P_NOTI token instead.
  // Only this fixed same-origin route reaches the top frame; no provider values
  // or sensitive payment tokens are reflected or placed in the redirect URL.
  const nonce=crypto.randomBytes(18).toString('base64');
  res.setHeader('Content-Type','text/html; charset=utf-8');
  res.setHeader('Content-Security-Policy',`default-src 'none'; script-src 'nonce-${nonce}'; frame-ancestors 'self'; base-uri 'none'`);
  res.end(`<!doctype html><html lang="ko"><meta charset="utf-8"><title>주문 상태 확인</title><p>주문 상태를 확인하고 있습니다.</p><a href="${target}" target="_top">주문 조회로 이동</a><script nonce="${nonce}">window.top.location.replace(${JSON.stringify(target)});</script></html>`);
 };
}
module.exports={parseBody,returnEndpoint};
