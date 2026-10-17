const {runtime}=require('../server/commerce/runtime.cjs');
const {returnEndpoint}=require('../server/commerce/toss-return.cjs');
const {context}=require('../server/commerce/test-context.cjs');
module.exports=async(req,res)=>{try{const {env}=context(req);return returnEndpoint(()=>runtime(env).service)(req,res);}catch{return res.status(503).send('결제 결과를 확인하고 있습니다. 주문 조회를 확인해주세요.');}};
