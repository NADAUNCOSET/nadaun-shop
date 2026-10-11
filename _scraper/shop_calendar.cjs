// Reuses the existing 장비렌탈 OAuth account on this PC. No customer data is logged.
'use strict';
const fs=require('node:fs'),path=require('node:path');
const {database}=require('../server/commerce/d1.cjs');
const {calendarService}=require('../server/commerce/calendar.cjs');
const root=path.resolve(__dirname,'..'),privateRoot=path.join(root,'_private/commerce');
async function googleClient(directory,fetcher=fetch){
 const token=JSON.parse(fs.readFileSync(path.join(directory,'token.json'),'utf8'));
 const text=fs.readFileSync(path.join(directory,'.env'),'utf8'),match=text.match(/^GCAL_CALENDAR_ID\s*=\s*(.+)$/m);
 if(!match)throw Error('calendar_not_configured');
 const calendarId=match[1].trim().replace(/^['"]|['"]$/g,'');
 const auth=await fetcher(token.token_uri||'https://oauth2.googleapis.com/token',{method:'POST',body:new URLSearchParams({client_id:token.client_id,client_secret:token.client_secret,refresh_token:token.refresh_token,grant_type:'refresh_token'}),signal:AbortSignal.timeout(20000)});
 const data=await auth.json();if(!auth.ok||!data.access_token)throw Error('calendar_oauth_unavailable');
 const base='https://www.googleapis.com/calendar/v3/calendars/'+encodeURIComponent(calendarId);
 async function call(suffix,method='GET',body=null,etag=null){
  const response=await fetcher(base+suffix,{method,headers:{Authorization:'Bearer '+data.access_token,'Content-Type':'application/json',...(etag?{'If-Match':etag}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(20000)});
  if(method==='GET'&&[404,410].includes(response.status))return null;
  if(!response.ok){const error=Error('calendar_api_unavailable');error.status=response.status;throw error;}
  return response.status===204?null:response.json();
 }
 return {get:id=>call('/events/'+encodeURIComponent(id)),insert:body=>call('/events?sendUpdates=none','POST',body),patch:(id,body,etag)=>call('/events/'+encodeURIComponent(id)+'?sendUpdates=none','PATCH',body,etag),remove:(id,etag)=>call('/events/'+encodeURIComponent(id)+'?sendUpdates=none','DELETE',null,etag)};
}
async function main(){
 const env=JSON.parse(fs.readFileSync(path.join(privateRoot,'configuration.json'),'utf8'));
 const directory=env.SHOP_CALENDAR_OAUTH_DIRECTORY;
 if(!directory)throw Error('calendar_directory_missing');
 const db=database(env),client=await googleClient(directory),result=await calendarService({db,dataKey:env.SHOP_ORDER_DATA_KEY,client}).drain(25);
 const problems=(await db.query("SELECT COUNT(*) AS n FROM shop_calendar_sync WHERE status IN ('error','review')"))[0].n;
 await db.query("INSERT INTO shop_calendar_health(id,status,checked_at) VALUES('calendar',?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,checked_at=excluded.checked_at",[problems?'error':'connected',Date.now()]);
 const status={checked_at:new Date().toISOString(),state:'checked',...result};
 fs.writeFileSync(path.join(privateRoot,'calendar-status.json'),JSON.stringify(status)+'\n',{mode:0o600});
 process.stdout.write(JSON.stringify(status)+'\n');
}
if(require.main===module)main().catch(async()=>{
 try{const env=JSON.parse(fs.readFileSync(path.join(privateRoot,'configuration.json'),'utf8'));await database(env).query("INSERT INTO shop_calendar_health(id,status,checked_at) VALUES('calendar','error',?) ON CONFLICT(id) DO UPDATE SET status='error',checked_at=excluded.checked_at",[Date.now()]);}catch{}
 fs.writeFileSync(path.join(privateRoot,'calendar-status.json'),JSON.stringify({checked_at:new Date().toISOString(),state:'error',error:'calendar_or_storage_unavailable'})+'\n',{mode:0o600});process.stderr.write('Calendar connection needs review; credentials and customer data are not logged.\n');process.exitCode=1;
});
module.exports={googleClient};
