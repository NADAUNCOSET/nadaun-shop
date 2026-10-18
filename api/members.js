'use strict';
const {runtime}=require('../server/commerce/runtime.cjs');
const {context}=require('../server/commerce/test-context.cjs');
const {memberEndpoint}=require('../server/commerce/member-http.cjs');
const handlers=new Map();
module.exports=async(req,res)=>{try{const {env,cookiePrefix,testing}=context(req),key=testing?'qa':'live';let handler=handlers.get(key);if(!handler){const {members,repo,crm}=runtime(env);handler=memberEndpoint({members,repo,crm,sessionKey:env.SHOP_SESSION_KEY,adminPasswordEmail:env.SHOP_ADMIN_EMAIL,cookiePrefix,testing});handlers.set(key,handler);}return handler(req,res);}catch{return res.status(503).json({error:'회원 서비스 연결을 확인하고 있습니다.'});}};
