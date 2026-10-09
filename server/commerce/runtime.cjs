'use strict';
const fs=require('node:fs');
const path=require('node:path');
const {database}=require('./d1.cjs');
const {repository,orderService}=require('./orders.cjs');
const {documentService}=require('./documents.cjs');
const {popbill}=require('./popbill.cjs');
const {inicis}=require('./inicis.cjs');
const {adminService}=require('./admin.cjs');
let cached;
function runtime(env=process.env){
 if(cached)return cached;
 if(!env.SHOP_ADMIN_PASSWORD_HASH)throw Error('Admin not configured');
 const catalog=JSON.parse(fs.readFileSync(path.join(process.cwd(),'data/catalog/catalog.json'),'utf8')),cache=new Map();
 function detail(p){
  if(!/^[a-f0-9]{2}$/.test(p.detail_bucket))throw Error('Invalid detail shard');
  if(!cache.has(p.detail_bucket))cache.set(p.detail_bucket,JSON.parse(fs.readFileSync(path.join(process.cwd(),'data/catalog/details',p.detail_bucket+'.json'),'utf8')));
  const d=cache.get(p.detail_bucket)[p.id];if(!d)throw Error('Missing detail');return d;
 }
 const db=database(env),repo=repository(db);
 let payment=null,invoice=null;
 if(env.SHOP_ORDERS_ENABLED==='true'){payment=inicis(env);invoice=popbill(env);}
 const documents=documentService({db,repo,dataKey:env.SHOP_ORDER_DATA_KEY,payment,invoice});
 const service=orderService({repo,catalog,detail,dataKey:env.SHOP_ORDER_DATA_KEY,sessionKey:env.SHOP_SESSION_KEY,payment,documents,invoiceEnabled:!!invoice});
 const admin=adminService({db,service,dataKey:env.SHOP_ORDER_DATA_KEY});
 cached={repo,service,payment,documents,admin};return cached;
}
module.exports={runtime};
