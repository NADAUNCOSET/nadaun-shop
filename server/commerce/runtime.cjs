'use strict';
const fs=require('node:fs');
const path=require('node:path');
const {database}=require('./d1.cjs');
const {repository,orderService}=require('./orders.cjs');
const {documentService}=require('./documents.cjs');
const {popbill}=require('./popbill.cjs');
const {toss}=require('./toss.cjs');
const {adminService}=require('./admin.cjs');
const {adminDraftService}=require('./admin-drafts.cjs');
const {goodsflow}=require('./goodsflow.cjs');
const {memberService}=require('./members.cjs');
const cached=new Map();
function runtime(env=process.env){
 const cacheKey=env.SHOP_TEST_CONTEXT==='true'?'qa':'live';if(cached.has(cacheKey))return cached.get(cacheKey);
 if(!env.SHOP_ADMIN_PASSWORD_HASH)throw Error('Admin not configured');
 const catalog=JSON.parse(fs.readFileSync(path.join(process.cwd(),'data/catalog/catalog.json'),'utf8')),cache=new Map();
 function detail(p){
  if(!/^[a-f0-9]{2}$/.test(p.detail_bucket))throw Error('Invalid detail shard');
  if(!cache.has(p.detail_bucket))cache.set(p.detail_bucket,JSON.parse(fs.readFileSync(path.join(process.cwd(),'data/catalog/details',p.detail_bucket+'.json'),'utf8')));
  const d=cache.get(p.detail_bucket)[p.id];if(!d)throw Error('Missing detail');return d;
 }
 const db=database(env),repo=repository(db);
 let payment=null,invoice=null;
 if(env.SHOP_ORDERS_ENABLED==='true'){payment=toss(env);if(cacheKey!=='qa')invoice=popbill(env);}
 const documents=documentService({db,repo,dataKey:env.SHOP_ORDER_DATA_KEY,payment,invoice});
 const service=orderService({repo,catalog,detail,dataKey:env.SHOP_ORDER_DATA_KEY,sessionKey:env.SHOP_SESSION_KEY,payment,documents,labelProvider:cacheKey==='qa'?null:goodsflow(env),invoiceEnabled:!!invoice,testing:cacheKey==='qa'});
 const admin=adminService({db,service,dataKey:env.SHOP_ORDER_DATA_KEY});
 const drafts=adminDraftService({db,catalog,detail,dataKey:env.SHOP_ORDER_DATA_KEY});
 const bps=Number(env.SHOP_POINTS_EARN_BPS||0);if(!Number.isSafeInteger(bps)||bps<0||bps>1000)throw Error('Invalid points policy');
 const members=memberService({db,repo,dataKey:env.SHOP_ORDER_DATA_KEY,sessionKey:env.SHOP_SESSION_KEY,enabled:env.SHOP_MEMBERS_ENABLED==='true',earnBasisPoints:bps,testing:cacheKey==='qa'});
 const value={repo,service,payment,documents,admin,drafts,members};cached.set(cacheKey,value);return value;
}
module.exports={runtime};
