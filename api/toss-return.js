const {runtime}=require('../server/commerce/runtime.cjs');
const {returnEndpoint}=require('../server/commerce/toss-return.cjs');
module.exports=returnEndpoint(()=>runtime().service);
