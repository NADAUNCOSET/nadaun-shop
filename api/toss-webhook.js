const {runtime}=require('../server/commerce/runtime.cjs');
const {webhookEndpoint}=require('../server/commerce/payment-webhook.cjs');
module.exports=webhookEndpoint(()=>runtime());
