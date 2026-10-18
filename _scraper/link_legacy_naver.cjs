'use strict';
const fs=require('node:fs'),path=require('node:path');
const {database}=require('../server/commerce/d1.cjs');
const {hash}=require('../server/commerce/security.cjs');
const {prepareNaverLinks,applyNaverLinks}=require('./lib/naver_member_link.cjs');
const root=path.resolve(__dirname,'..'),out=path.join(root,'_private/commerce/social-login-20261017/naver-live-20261018');
async function main(){
 const action=process.argv[2]||'plan';if(!['plan','apply'].includes(action))throw Error('Unknown action.');
 const env=JSON.parse(fs.readFileSync(path.join(root,'_private/commerce/configuration.json'))),input=JSON.parse(fs.readFileSync(path.join(root,'_private/commerce/member-migration-20261018/input.private.json')));
 const receipt=JSON.parse(fs.readFileSync(path.join(out,'credential-import.json')));
 if(!receipt.client_id_matches_existing_imweb||!receipt.secret_matches_existing_imweb||hash(fs.readFileSync(path.join(root,'_private/commerce/member-migration-20261018/original-members.xls')))!==input.source.file_sha256)throw Error('Existing application/source verification required.');
 const db=database(env),options={input,dataKey:env.SHOP_ORDER_DATA_KEY,sessionKey:env.SHOP_SESSION_KEY,clientId:env.SHOP_OAUTH_NAVER_CLIENT_ID,confirmedExistingClientId:'3BSuy09EqFAv59wVOq9m'};
 const members=await db.query('SELECT * FROM shop_members'),identities=await db.query('SELECT * FROM shop_social_identities'),plan=prepareNaverLinks({...options,members,identities});
 let result={at:new Date().toISOString(),action,total:plan.links.length,already_present:plan.existing,source_sha256:plan.source_sha256};
 if(action==='apply'){
  if(env.SHOP_OAUTH_NAVER_ENABLED==='true')throw Error('Complete reconciliation before first Naver activation.');
  const backup=path.join(out,'identity-link-before.private.json');if(!fs.existsSync(backup))fs.writeFileSync(backup,JSON.stringify({members,identities}),{mode:0o600,flag:'wx'});
  result={...result,...await applyNaverLinks(db,options)};
 }
 fs.writeFileSync(path.join(out,'identity-link-'+action+'.json'),JSON.stringify(result,null,2)+'\n',{mode:0o600});console.log(JSON.stringify(result));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
