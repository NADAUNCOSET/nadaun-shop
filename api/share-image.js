const fs=require('node:fs');
const path=require('node:path');
const {createImageHandler}=require('../server/share-image.cjs');
const catalogs=new Map();
function productFor(kind,id){
 if(!catalogs.has(kind)){
  const data=JSON.parse(fs.readFileSync(path.join(process.cwd(),'data',kind==='gift'?'gift':'catalog','catalog.json'),'utf8'));
  catalogs.set(kind,{products:new Map(data.products.map(p=>[p.id,p])),redirects:data.redirects||{}});
 }
 const {products,redirects}=catalogs.get(kind);
 return products.get(Object.hasOwn(redirects,id)?redirects[id]:id);
}
module.exports=createImageHandler({productFor});
