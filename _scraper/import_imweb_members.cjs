'use strict';
// Read-only by default. All customer inputs, snapshots and receipts remain private.
const fs=require('node:fs'),path=require('node:path');
const {database}=require('../server/commerce/d1.cjs');
const {hash}=require('../server/commerce/security.cjs');
const {prepareImport,preflight,applyImport,verifyImport}=require('./lib/imweb_member_import.cjs');
const root=path.resolve(__dirname,'..'),directory=path.join(root,'_private/commerce/member-migration-20261018');
function save(name,value){fs.writeFileSync(path.join(directory,name),JSON.stringify(value,null,2)+'\n',{mode:0o600});}
async function main(){
 const command=process.argv[2]||'plan';if(!['plan','apply','verify'].includes(command))throw Error('Unknown command.');
 const env=JSON.parse(fs.readFileSync(path.join(root,'_private/commerce/configuration.json'),'utf8'));
 const input=JSON.parse(fs.readFileSync(path.join(directory,'input.private.json'),'utf8'));
 if(hash(fs.readFileSync(path.join(directory,'original-members.xls')))!==input.source.file_sha256)throw Error('Source backup verification failed.');
 const options={dataKey:env.SHOP_ORDER_DATA_KEY,sessionKey:env.SHOP_SESSION_KEY,kakaoAppId:'415972',kakaoClientId:env.SHOP_OAUTH_KAKAO_CLIENT_ID};
 const plan=prepareImport(input,options),db=database(env);
 const before=await preflight(db,plan,options.dataKey);
 if(command==='plan'){
  const result={at:new Date().toISOString(),source_sha256:plan.source_sha256,...plan.counts,...before,naver_status:'held until original Naver Login application and legacy identifier format are verified',passwords_exported:false,current_policy_consent_claimed:false};
  save('plan-summary.json',result);console.log(JSON.stringify(result));return;
 }
 if(command==='apply'){
  if(['KAKAO','GOOGLE','NAVER'].some(p=>env['SHOP_OAUTH_'+p+'_ENABLED']==='true'))throw Error('Pause provider activation until migration reconciliation is complete.');
  const backup=path.join(directory,'production-before.private.json');
  if(!fs.existsSync(backup)){
   const tables={};for(const table of ['shop_members','shop_social_identities','shop_member_sessions','shop_points'])tables[table]=await db.query('SELECT * FROM '+table);
   fs.writeFileSync(backup,JSON.stringify({at:new Date().toISOString(),tables}),{mode:0o600,flag:'wx'});
  }
  const result=await applyImport(db,plan,options.dataKey,{onProgress:n=>{if(n%60===0)console.log(JSON.stringify({namespace:'production',processed:n,total:plan.counts.members}));}});
  const receipt={at:new Date().toISOString(),namespace:'production',source_sha256:plan.source_sha256,...result,social_login_live_verified:false,provider_activation_changed:false};
  save('production-receipt.json',receipt);console.log(JSON.stringify(receipt));return;
 }
 const result={at:new Date().toISOString(),...await verifyImport(db,plan,options.dataKey)};save('production-reverification.json',result);console.log(JSON.stringify(result));
}
main().catch(()=>{console.error('Member migration stopped. Source and existing accounts were not overwritten; inspect private receipts. No customer values logged.');process.exitCode=1;});
