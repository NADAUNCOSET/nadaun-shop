const {runtime}=require('../server/commerce/runtime.cjs');
const {returnEndpoint}=require('../server/commerce/inicis-return.cjs');
module.exports=returnEndpoint(()=>runtime().service);
