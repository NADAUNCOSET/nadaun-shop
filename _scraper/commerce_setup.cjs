// Configuration stays in the project's Git/deployment-excluded _private tree.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {passwordHash}=require('../server/commerce/security.cjs');
const {database}=require('../server/commerce/d1.cjs');
const {toss}=require('../server/commerce/toss.cjs');
const root=path.resolve(__dirname,'..');
const directory=path.join(root,'_private','commerce');
const file=path.join(directory,'configuration.json');
const fields=['SHOP_CF_ACCOUNT_ID','SHOP_D1_DATABASE_ID','SHOP_D1_API_TOKEN','SHOP_ORDER_DATA_KEY','SHOP_SESSION_KEY','SHOP_ADMIN_PASSWORD_HASH','SHOP_PAYMENT_MODE','SHOP_TOSS_CLIENT_KEY','SHOP_TOSS_SECRET_KEY'];
async function main(){
 const command=process.argv[2]||'check';
 if(command==='init'){
  fs.mkdirSync(directory,{recursive:true,mode:0o700});
  if(fs.existsSync(file))throw Error('Configuration already exists; nothing overwritten.');
  const password=crypto.randomBytes(24).toString('base64url');
  const env=Object.fromEntries(fields.map(k=>[k,'']));
  Object.assign(env,{SHOP_ORDERS_ENABLED:'false',SHOP_ORDER_DATA_KEY:crypto.randomBytes(32).toString('hex'),SHOP_SESSION_KEY:crypto.randomBytes(32).toString('hex'),SHOP_ADMIN_PASSWORD_HASH:await passwordHash(password)});
  fs.writeFileSync(file,JSON.stringify(env,null,2)+'\n',{flag:'wx',mode:0o600});
  fs.writeFileSync(path.join(directory,'owner-login.private'),password+'\n',{flag:'wx',mode:0o600});
  process.stdout.write('Private configuration created. Orders remain disabled.\n');return;
 }
 if(!fs.existsSync(file)){process.stdout.write(JSON.stringify({configured:false,missing:fields,ordersEnabled:false})+'\n');return;}
 const env=JSON.parse(fs.readFileSync(file,'utf8'));
 const missing=fields.filter(k=>!env[k]);
 if(command==='schema'){
  const db=database(env);
  const sql=fs.readFileSync(path.join(root,'server/commerce/schema.sql'),'utf8').split(';').map(s=>s.trim()).filter(Boolean);
  await db.batch(sql.map(sql=>({sql,params:[]})));
  const tables=await db.query("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('shop_orders','shop_order_events','shop_rate_limits')");
  if(tables.length!==3)throw Error('Schema verification failed.');
  process.stdout.write('Three private order tables verified. Orders remain gated by configuration.\n');return;
 }
 if(command!=='check')throw Error('Use init, check or schema.');
 const result={configured:missing.length===0,missing,ordersEnabled:env.SHOP_ORDERS_ENABLED==='true',paymentMode:env.SHOP_PAYMENT_MODE||null,databaseVerified:false};
 if(!missing.length){toss(env);const tables=await database(env).query("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('shop_orders','shop_order_events','shop_rate_limits')");result.databaseVerified=tables.length===3;}
 process.stdout.write(JSON.stringify(result)+'\n');
}
main().catch(()=>{process.stderr.write('Commerce setup could not complete. Check private configuration and service access; values are not logged.\n');process.exitCode=1;});
