'use strict';
const {ShopError,hash,random,sessions,passwordMatches}=require('./security.cjs');
function endpoint({service,repo,sessionKey,password,enabled=true,origin='https://shop.nadaun.co',clock=()=>Date.now()}){
 const session=sessions(sessionKey,clock);
 const cookie=(role,token,seconds)=>`__Host-nadaun-${role}=${token}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=${seconds}`;
 const cookies=req=>Object.fromEntries(String(req.headers.cookie||'').split(';').map(v=>v.trim().split('=')));
 return async function handler(req,res){
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex');res.setHeader('Content-Type','application/json; charset=utf-8');
  try{
   const url=new URL(req.url,origin),action=url.searchParams.get('action')||'config';
   if(!['GET','POST'].includes(req.method)){res.setHeader('Allow','GET, POST');throw new ShopError(405,'허용되지 않은 요청입니다.');}
   if(req.method==='GET'&&action==='config')return res.status(200).json({ordersEnabled:enabled});
   if(!enabled)throw new ShopError(503,'주문 서비스 연결을 준비 중입니다.');
   if(req.method==='POST'&&req.headers.origin!==origin)throw new ShopError(403,'사이트에서 다시 요청해주세요.');
   const ip=String(req.headers['x-forwarded-for']||'unknown').split(',')[0].trim();
   await repo.limit(hash(sessionKey+ip),120,60);
   const stored=cookies(req);
   const admin=session.read(stored['__Host-nadaun-admin'],'admin');
   let customer=session.read(stored['__Host-nadaun-customer'],'customer');
   let input=req.body;
   if(req.method==='POST'){
    if(typeof input==='string'){if(Buffer.byteLength(input)>32768)throw new ShopError(413,'요청 내용이 너무 큽니다.');try{input=JSON.parse(input);}catch{throw new ShopError(400,'요청 형식을 확인해주세요.');}}
    if(!input||typeof input!=='object'||Array.isArray(input)||Buffer.byteLength(JSON.stringify(input))>32768)throw new ShopError(400,'요청 형식을 확인해주세요.');
   }
   if(action==='login'&&req.method==='POST'){
    await repo.limit('login:'+hash(sessionKey+ip),10,900);
    if(!await passwordMatches(input.password,password))throw new ShopError(401,'로그인 정보를 확인해주세요.');
    res.setHeader('Set-Cookie',cookie('admin',session.issue('owner','admin',8*3600),8*3600));return res.status(200).json({authenticated:true});
   }
   if(action==='logout'&&req.method==='POST'){res.setHeader('Set-Cookie',cookie('admin','',0));return res.status(200).json({authenticated:false});}
   if(action.startsWith('admin-')){
    if(!admin)throw new ShopError(401,'관리자 로그인이 필요합니다.');
    if(action==='admin-orders'&&req.method==='GET')return res.status(200).json({orders:await service.adminList()});
    if(action==='admin-events'&&req.method==='GET')return res.status(200).json({events:await repo.events(url.searchParams.get('id'))});
    if(req.method==='POST'){
     const fn={'admin-approve':'approve','admin-ship':'ship','admin-reconcile':'reconcile'}[action];
     if(fn)return res.status(200).json({order:await service[fn](input.id,input)});
    }
    throw new ShopError(404,'요청을 찾을 수 없습니다.');
   }
   if(action==='session'&&req.method==='POST'){
    if(!customer){customer=random();res.setHeader('Set-Cookie',cookie('customer',session.issue(customer,'customer',30*86400),30*86400));}
    return res.status(200).json({ready:true});
   }
   if(!customer)throw new ShopError(401,'주문한 브라우저에서 다시 접속해주세요.');
   const owner=hash(customer);
   if(action==='orders'&&req.method==='GET')return res.status(200).json({orders:await service.list(owner)});
   if(action==='order'&&req.method==='GET')return res.status(200).json({order:await service.get(url.searchParams.get('id'),owner)});
   if(action==='create'&&req.method==='POST'){
    await repo.limit('create:'+owner,10,3600);
    return res.status(201).json({order:await service.create(owner,req.headers['idempotency-key'],input)});
   }
   if(action==='start'&&req.method==='POST')return res.status(200).json(await service.start(input.id,owner,input.quote_version));
   if(action==='confirm'&&req.method==='POST')return res.status(200).json({order:await service.confirm(input.id,owner,input)});
   throw new ShopError(404,'요청을 찾을 수 없습니다.');
  }catch(error){return res.status(error instanceof ShopError?error.status:503).json({error:error instanceof ShopError?error.message:'주문 처리를 확인하고 있습니다. 잠시 후 다시 시도해주세요.'});}
 };
}
module.exports={endpoint};
