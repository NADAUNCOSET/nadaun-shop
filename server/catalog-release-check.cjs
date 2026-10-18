'use strict';
// Runs on every Vercel deployment, including releases that only change UI.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const digest=value=>crypto.createHash('sha256').update(value).digest('hex');
const idsDigest=ids=>digest([...ids].sort().join('\n'));

function validateCatalog(catalog,policy={}){
  const errors=[];
  const fail=(message,id='')=>errors.push(message+(id?': '+id:''));
  const index=(rows,label)=>{
    const result=new Map();
    for(const row of rows||[]){
      if(!row.id||result.has(row.id))fail('Duplicate/missing '+label,row.id);
      result.set(row.id,row);
    }
    return result;
  };
  const brands=index(catalog.brands,'brand'),categories=index(catalog.categories,'category');
  const products=index(catalog.products,'product'),families=new Set(),offers=new Map();
  const positions=new Map();
  for(const c of categories.values()){
    const seen=new Set([c.id]);let parent=c.parent_id;
    while(parent){
      if(seen.has(parent)){fail('Category cycle',c.id);break}
      seen.add(parent);const ancestor=categories.get(parent);
      if(!ancestor){fail('Missing category parent',c.id);break}
      if(ancestor.brand_id!==c.brand_id)fail('Cross-brand category ancestry',c.id);
      parent=ancestor.parent_id;
    }
    if(c.brand_id&&!brands.has(c.brand_id))fail('Unknown category brand',c.id);
    if(policy.require_positions){
      if(!Number.isInteger(c.navigation_position)||c.navigation_position<0)fail('Missing category position',c.id);
      const key=c.parent_id||'';
      const last=positions.get(key)??-1;
      if(c.navigation_position!==last+1)fail('Unstable sibling order',c.id);
      positions.set(key,c.navigation_position);
    }
  }
  const listingCounts=new Map();
  for(const p of products.values()){
    if(!brands.has(p.brand_id))fail('Unknown product brand',p.id);
    const fid=p.listing_id||p.id;families.add(fid);
    const first=products.get(fid);
    if(!first||first.brand_id!==p.brand_id||first.kind!==p.kind)fail('Invalid product family',p.id);
    if(p.id===fid){const key=p.brand_id+'|'+p.kind;listingCounts.set(key,(listingCounts.get(key)||0)+1)}
    for(const field of ['category_ids','type_ids','promotion_ids']){
      const values=p[field]||[];
      if(new Set(values).size!==values.length)fail('Repeated '+field,p.id);
      for(const cid of values)if(!categories.has(cid))fail('Unknown '+field,p.id+'/'+cid);
    }
    const nav=p.kind==='purchase'?p.navigation_category_ids:p.category_ids;
    if(p.kind==='purchase'){
      if(!nav?.length)fail('Unclassified purchase brand menu',p.id);
      const allowed=new Set(brands.get(p.brand_id)?.navigation_category_ids||[]);
      for(const cid of nav||[]){
        const c=categories.get(cid);
        if(!c||c.brand_id!==p.brand_id||!allowed.has(cid))fail('Wrong brand menu membership',p.id+'/'+cid);
        if(c?.navigation_role==='collection')fail('Collection mixed into product category',p.id+'/'+cid);
        if(c?.parent_id&&!nav.includes(c.parent_id))fail('Incomplete menu ancestry',p.id+'/'+cid);
      }
    }
    const scope=p.kind==='rental'?'rental-product':'product';
    const types=(p.type_ids||[]).filter(cid=>categories.get(cid)?.scope===scope);
    if(!types.length)fail('Missing product-type classification',p.id);
    for(const cid of types){const c=categories.get(cid);if(c.parent_id&&!types.includes(c.parent_id))fail('Incomplete product-type ancestry',p.id+'/'+cid)}
    const primary=(p.offers||[]).filter(o=>o.id===p.id);
    if(primary.length!==1)fail('Untraceable primary offer',p.id);
    for(const o of p.offers||[]){
      if(offers.has(o.id))fail('Duplicate supplier product',o.id);
      offers.set(o.id,{...o,product_id:p.id});
    }
    const preferred=policy.primary_sources?.[p.brand_id];
    if(preferred&&(p.offers||[]).some(o=>o.source===preferred)&&primary[0]?.source!==preferred)fail('Wrong preferred supplier',p.id);
  }
  if(catalog.meta.product_count!==products.size)fail('Product total mismatch');
  if(catalog.meta.listing_count!==families.size)fail('Listing total mismatch');
  for(const b of brands.values())for(const kind of ['purchase','rental']){
    if(b[kind+'_count']!==(listingCounts.get(b.id+'|'+kind)||0))fail('Brand count mismatch',b.id+'/'+kind);
  }
  for(const [old,target] of Object.entries(catalog.redirects||{})){
    if(products.has(old)||old===target||!products.has(target))fail('Broken duplicate redirect',old);
  }
  for(const [source,expected] of Object.entries(policy.source_inventories||{})){
    const ids=[...offers.values()].filter(o=>o.source===source).map(o=>o.id);
    if(ids.length!==expected.count||idsDigest(ids)!==expected.sha256)fail('Incomplete source inventory',source);
  }
  if(policy.brand_order&&JSON.stringify(catalog.brands.map(b=>b.id))!==JSON.stringify(policy.brand_order))fail('Brand order differs from reviewed release');
  return errors;
}

function checkRelease(root){
  const read=p=>JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
  const policy=read('server/catalog-release.json');
  if(policy.schema_version!==1)throw Error('Unsupported catalogue release manifest');
  const catalog=read('data/catalog/catalog.json');
  const errors=validateCatalog(catalog,policy);
  if(catalog.meta.revision!==policy.revision)errors.push('Release revision mismatch');
  for(const file of ['data/catalog/brands.json','data/catalog/rental.json','data/catalog/sync-status.json']){
    const value=read(file);
    if((value.meta||value).revision!==policy.revision)errors.push('Mixed release revision: '+file);
  }
  for(const b of catalog.brands){
    if(!/^[a-z0-9-]+$/.test(b.id)||!fs.existsSync(path.join(root,'brands',b.id+'.html')))errors.push('Missing brand route: '+b.id);
  }
  for(const [file,expected] of Object.entries(policy.files||{})){
    if(file.includes('..')||path.isAbsolute(file))throw Error('Unsafe release path');
    try{if(digest(fs.readFileSync(path.join(root,file)))!==expected)errors.push('Changed release artifact: '+file)}
    catch{errors.push('Missing release artifact: '+file)}
  }
  const buckets=new Map();
  for(const p of catalog.products){
    const file='data/catalog/details/'+p.detail_bucket+'.json';
    if(!policy.files[file])errors.push('Unverified product detail bucket: '+p.id);
    else{
      if(!buckets.has(file))buckets.set(file,read(file));
      if(!buckets.get(file)[p.id])errors.push('Missing product detail: '+p.id);
    }
  }
  if(errors.length)throw Error('Catalogue release blocked ('+errors.length+'):\n'+errors.slice(0,30).join('\n'));
  return {revision:catalog.meta.revision,products:catalog.products.length,brands:catalog.brands.length,categories:catalog.categories.length,verified_files:Object.keys(policy.files).length};
}
module.exports={validateCatalog,checkRelease,idsDigest};
if(require.main===module){
  try{console.log(JSON.stringify({catalogue_release:'passed',...checkRelease(path.resolve(__dirname,'..'))}))}
  catch(error){console.error(error.message);process.exitCode=1}
}
