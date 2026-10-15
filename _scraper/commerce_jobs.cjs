// NAS worker: recovers payment documents and polls existing shipping bookings.
// Private configuration is never logged; every external issue requires PAID.
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..'),folder=path.join(root,'_private/commerce');
async function main(){
 const file=path.join(folder,'configuration.json');
 if(!fs.existsSync(file))return;
 const env=JSON.parse(fs.readFileSync(file,'utf8'));
 process.chdir(root);
 let result={state:'disabled',processed:0};
 if(env.SHOP_ORDERS_ENABLED==='true'){
  const {runtime}=require('../server/commerce/runtime.cjs');
  const current=runtime(env);
  result={state:'checked',...await current.documents.drain(10),shipping:await current.service.labelDrain()};
 }
 fs.writeFileSync(path.join(folder,'jobs-status.json'),JSON.stringify({checked_at:new Date().toISOString(),...result})+'\n',{mode:0o600});
}
main().catch(()=>{
 fs.mkdirSync(folder,{recursive:true});
 fs.writeFileSync(path.join(folder,'jobs-status.json'),JSON.stringify({checked_at:new Date().toISOString(),state:'error',error:'configuration_or_provider_unavailable'})+'\n',{mode:0o600});
 process.exitCode=1;
});
