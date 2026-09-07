'use strict';
const {ShopError}=require('./security.cjs');
function database(env,fetcher=fetch){
 if(!/^[a-f0-9]{32}$/i.test(env.SHOP_CF_ACCOUNT_ID||'')||!/^[a-f0-9-]{36}$/i.test(env.SHOP_D1_DATABASE_ID||'')||!env.SHOP_D1_API_TOKEN)throw new ShopError(503,'주문 서비스 연결을 준비 중입니다.');
 const url=`https://api.cloudflare.com/client/v4/accounts/${env.SHOP_CF_ACCOUNT_ID}/d1/database/${env.SHOP_D1_DATABASE_ID}/query`;
 async function batch(statements){
  let response,data;
  try{response=await fetcher(url,{method:'POST',headers:{Authorization:`Bearer ${env.SHOP_D1_API_TOKEN}`,'Content-Type':'application/json'},body:JSON.stringify({batch:statements}),signal:AbortSignal.timeout(12000)});data=await response.json();}catch{throw new ShopError(503,'주문 저장소의 응답을 확인하지 못했습니다. 같은 요청으로 다시 시도해주세요.');}
  if(!response.ok||!data.success||data.result?.length!==statements.length||data.result.some(r=>!r.success))throw new ShopError(503,'주문 저장소를 확인하고 있습니다. 잠시 후 다시 시도해주세요.');
  return data.result.map(r=>r.results||[]);
 }
 return {batch,query:async(sql,params=[])=> (await batch([{sql,params}]))[0]};
}
module.exports={database};
