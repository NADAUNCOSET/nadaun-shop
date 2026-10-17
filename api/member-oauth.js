'use strict';
const {runtime}=require('../server/commerce/runtime.cjs');
const {context}=require('../server/commerce/test-context.cjs');
const {socialEndpoint}=require('../server/commerce/social-http.cjs');
const handlers=new Map();
module.exports=async(req,res)=>{try{const {env,cookiePrefix,testing}=context(req),key=testing?'qa':'live';let handler=handlers.get(key);if(!handler){const {social,members,repo}=runtime(env);handler=socialEndpoint({social,members,repo,sessionKey:env.SHOP_SESSION_KEY,cookiePrefix,testing});handlers.set(key,handler);}return handler(req,res);}catch{res.setHeader('Cache-Control','no-store');return res.status(503).json({error:'간편로그인 연결을 확인하고 있습니다.'});}};
