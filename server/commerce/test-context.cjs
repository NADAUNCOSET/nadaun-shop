'use strict';
const crypto=require('node:crypto');
const {sessions}=require('./security.cjs');
const MODE_COOKIE='__Host-nadaun-qa-mode';
const cookieValue=(req,name)=>String(req.headers.cookie||'').split(';').map(s=>s.trim()).find(s=>s.startsWith(name+'='))?.slice(name.length+1)||'';
function context(req,base=process.env){
 const testing=base.SHOP_QA_ENABLED==='true'&&sessions(base.SHOP_SESSION_KEY).read(cookieValue(req,MODE_COOKIE),'storefront-qa')==='storefront-qa';
 if(!testing)return {env:base,testing:false,cookiePrefix:'nadaun'};
 const derive=role=>crypto.createHmac('sha256',base.SHOP_SESSION_KEY).update('storefront-qa:'+role).digest('hex');
 return {testing:true,cookiePrefix:'nadaun-qa',env:{...base,SHOP_TEST_CONTEXT:'true',SHOP_SESSION_KEY:derive('session'),SHOP_ORDER_DATA_KEY:derive('data'),SHOP_ORDERS_ENABLED:'true',SHOP_RENTAL_REQUESTS_ENABLED:'true',SHOP_GIFT_REQUESTS_ENABLED:'true',SHOP_MEMBERS_ENABLED:'true',SHOP_PAYMENT_MODE:'test',SHOP_TOSS_CLIENT_KEY:base.SHOP_QA_TOSS_CLIENT_KEY||'',SHOP_TOSS_SECRET_KEY:base.SHOP_QA_TOSS_SECRET_KEY||'',SHOP_TOSS_MID:'',SHOP_TOSS_LIVE_VERIFIED:'false',SHOP_POPBILL_ENABLED:'false',SHOP_POINTS_EARN_BPS:'100',SHOP_GOODSFLOW_ENABLED:'false'}};
}
module.exports={context,cookieValue,MODE_COOKIE};
