const fs=require('node:fs');
const path=require('node:path');
const {imageURL}=require('./share-metadata.cjs');
const WIDTH=1200,HEIGHT=630,MAX_BYTES=6*1024*1024,MAX_LOCAL_BYTES=8*1024*1024;
// Sources already approved for public product media. An ID can never turn this
// endpoint into an arbitrary URL proxy; each redirect is checked again.
const IMAGE_HOSTS=new Set(['media.nadaun.co','kppkpp.co.kr','shop-phinf.pstatic.net','www.l-mount.co.kr','image.fzonesports.co.kr','image3.compuzone.co.kr','www.plthink.com','se-cdn.djiits.com','stormsend1.djicdn.com','ecimg.cafe24img.com','onnoff.kr','ldnet.co.kr','comsmart.co.kr','cdn.imweb.me','img.echosting.cafe24.com','www.avx.co.kr','cloudfront.imggift.com','cdn.saeki.co.kr','cdn.dev.saeki.co.kr','www.saeki.co.kr','ai.esmplus.com','godomall.speedycdn.net','cdn-pro-web-221-144.cdn-nhncommerce.com']);
function allowedRemote(value){
 const normalized=imageURL(value);if(!normalized)return null;
 const u=new URL(normalized);
 return IMAGE_HOSTS.has(u.hostname)&&!u.port&&!u.hash?u:null;
}
function isRaster(buffer){
 return buffer.length>=12&&(buffer[0]===255&&buffer[1]===216&&buffer[2]===255||buffer.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))||/^GIF8[79]a/.test(buffer.subarray(0,6).toString())||buffer.subarray(0,4).toString()==='RIFF'&&buffer.subarray(8,12).toString()==='WEBP');
}
async function fetchImage(value,fetchImpl=fetch){
 let url=allowedRemote(value);if(!url)throw Error('unapproved_image_host');
 const signal=AbortSignal.timeout(8000);
 for(let redirects=0;redirects<=3;redirects++){
  // A source access denial is final. Do not retry with cookies, Referer or a
  // disguised crawler/browser identity to bypass its policy.
  const response=await fetchImpl(url.href,{redirect:'manual',signal,headers:{Accept:'image/jpeg,image/png,image/webp,image/gif'}});
  if([301,302,303,307,308].includes(response.status)){
   const location=response.headers.get('location');await response.body?.cancel();
   url=location?allowedRemote(new URL(location,url).href):null;
   if(!url)throw Error('unapproved_image_redirect');continue;
  }
  if(!response.ok){await response.body?.cancel();const error=Error('source_image_unavailable');error.status=response.status;throw error;}
  const declared=Number(response.headers.get('content-length'));
  if(declared>MAX_BYTES){await response.body?.cancel();throw Error('image_too_large');}
  const reader=response.body?.getReader();if(!reader)throw Error('empty_image');
  const chunks=[];let length=0;
  try{while(true){const {done,value}=await reader.read();if(done)break;length+=value.byteLength;if(length>MAX_BYTES){await reader.cancel();throw Error('image_too_large');}chunks.push(Buffer.from(value));}}finally{reader.releaseLock();}
  const buffer=Buffer.concat(chunks,length);if(!isRaster(buffer))throw Error('invalid_image_bytes');
  return buffer;
 }
 throw Error('too_many_image_redirects');
}
async function jpeg(buffer){
 const sharp=require('sharp');
 return sharp(buffer,{limitInputPixels:25000000,animated:false,failOn:'error'}).rotate()
  .resize(WIDTH,HEIGHT,{fit:'contain',background:'#ffffff',withoutEnlargement:false})
  .flatten({background:'#ffffff'}).jpeg({quality:85,mozjpeg:true}).toBuffer();
}
function createImageHandler({productFor,fetchImpl=fetch,render=jpeg,fallback=()=>fs.readFileSync(path.join(process.cwd(),'assets/shop/nadaun-logo.png'))}={}){
 const cache=new Map();
 return async function handler(req,res){
  res.setHeader('X-Content-Type-Options','nosniff');
  if(!['GET','HEAD'].includes(req.method)){res.setHeader('Allow','GET, HEAD');return res.status(405).end();}
  const params=new URL(req.url,'https://shop.nadaun.co').searchParams;
  const kind=params.get('kind'),id=params.get('id')||'';
  if(!['product','gift'].includes(kind)||!id||id.length>100||!/^[a-zA-Z0-9-]+$/.test(id))return res.status(404).end();
  const product=productFor(kind,id);if(!product)return res.status(404).end();
  const source=imageURL(product.image),key=source||'missing',now=Date.now();
  let result=cache.get(key);
  if(!result||result.expires<=now){
   let bytes,usedFallback=false,denied=false;
   try{
    if(source?.startsWith('https://shop.nadaun.co/assets/')){
     const relative=decodeURIComponent(new URL(source).pathname).slice(1);
     const asset=path.resolve(process.cwd(),relative),assetRoot=path.resolve(process.cwd(),'assets')+path.sep;
     if(!asset.startsWith(assetRoot))throw Error('invalid_local_image');
     const local=fs.readFileSync(asset);if(local.length>MAX_LOCAL_BYTES||!isRaster(local))throw Error('invalid_local_image');bytes=await render(local);
    }else bytes=await render(await fetchImage(source,fetchImpl));
   }catch(error){
    denied=[401,403,429].includes(error.status);
    // The brand fallback is only a degraded preview, not verified product media.
    usedFallback=true;
    try{bytes=await render(fallback());}catch{res.setHeader('Cache-Control','no-store');return res.status(503).end();}
   }
   result={bytes,usedFallback,denied,expires:now+(denied?21600000:usedFallback?600000:3600000)};
   cache.delete(key);cache.set(key,result);if(cache.size>24)cache.delete(cache.keys().next().value);
  }
  res.setHeader('Content-Type','image/jpeg');res.setHeader('Content-Length',result.bytes.length);
  res.setHeader('Cache-Control',result.usedFallback?(result.denied?'public, max-age=0, s-maxage=21600':'public, max-age=0, s-maxage=600'):'public, max-age=3600, s-maxage=86400, stale-while-revalidate=86400');
  res.setHeader('X-Nadaun-Share-Image',result.usedFallback?'fallback':'product');
  return res.status(200).end(req.method==='HEAD'?'':result.bytes);
 };
}
module.exports={WIDTH,HEIGHT,MAX_BYTES,IMAGE_HOSTS,allowedRemote,isRaster,fetchImage,jpeg,createImageHandler};
