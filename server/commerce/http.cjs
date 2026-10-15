'use strict';
const {ShopError,hash,random,sessions,passwordMatches,adminEmail,identityMatches}=require('./security.cjs');
function endpoint({service,repo,adminService=null,draftService=null,sessionKey,password,email='',enabled=true,rentalEnabled=false,origin='https://shop.nadaun.co',adminOrigins=['https://order.nadaun.co'],clock=()=>Date.now()}){
 const session=sessions(sessionKey,clock);
 const configuredEmail=email?adminEmail(email):null;
 if(email&&!configuredEmail)throw new ShopError(503,'관리자 로그인 설정을 확인해주세요.');
 const cookie=(role,token,seconds)=>`__Host-nadaun-${role}=${token}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=${seconds}`;
 const cookies=req=>Object.fromEntries(String(req.headers.cookie||'').split(';').map(v=>v.trim().split('=')));
 return async function handler(req,res){
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex');res.setHeader('Content-Type','application/json; charset=utf-8');
  try{
   const url=new URL(req.url,origin),action=url.searchParams.get('action')||'config';
   if(!['GET','POST'].includes(req.method)){res.setHeader('Allow','GET, POST');throw new ShopError(405,'허용되지 않은 요청입니다.');}
   if(req.method==='GET'&&action==='config')return res.status(200).json({ordersEnabled:enabled,rentalRequestsEnabled:rentalEnabled,adminEnabled:!!adminService,adminDraftsEnabled:!!draftService,adminLoginRequiresEmail:!!configuredEmail,paymentProvider:'inicis',taxInvoiceEnabled:service.invoiceEnabled===true});
   const adminAction=['login','logout'].includes(action)||action.startsWith('admin-');
   if(req.method==='POST'&&req.headers.origin!==origin&&!(adminAction&&adminOrigins.includes(req.headers.origin)))throw new ShopError(403,'사이트에서 다시 요청해주세요.');
   const ip=String(req.headers['x-forwarded-for']||'unknown').split(',')[0].trim();
   await repo.limit(hash(sessionKey+ip),120,60);
   const stored=cookies(req);
   const adminSubject=session.read(stored['__Host-nadaun-admin'],'admin');
   const admin=adminSubject&&(!configuredEmail||adminSubject===configuredEmail)?adminSubject:null;
   let customer=session.read(stored['__Host-nadaun-customer'],'customer');
   let input=req.body;
   if(req.method==='POST'){
    const limit=admin&&['admin-invoice-preview','admin-invoice-apply'].includes(action)?1500000:32768;
    if(typeof input==='string'){if(Buffer.byteLength(input)>limit)throw new ShopError(413,'요청 용량을 초과했습니다. 송장 파일은 1MiB까지 지원합니다.');try{input=JSON.parse(input);}catch{throw new ShopError(400,'요청 형식을 확인해주세요.');}}
    if(!input||typeof input!=='object'||Array.isArray(input))throw new ShopError(400,'요청 형식을 확인해주세요.');
    if(Buffer.byteLength(JSON.stringify(input))>limit)throw new ShopError(413,'요청 용량을 초과했습니다. 송장 파일은 1MiB까지 지원합니다.');
   }
   if(action==='login'&&req.method==='POST'){
    await repo.limit('login:'+hash(sessionKey+ip),10,900);
    // Always perform the password check even when the supplied email is wrong.
    const validPassword=await passwordMatches(input.password,password);
    if(!validPassword||configuredEmail&&!identityMatches(input.email,configuredEmail))throw new ShopError(401,'로그인 정보를 확인해주세요.');
    res.setHeader('Set-Cookie',cookie('admin',session.issue(configuredEmail||'owner','admin',8*3600),8*3600));return res.status(200).json({authenticated:true});
   }
   if(action==='logout'&&req.method==='POST'){res.setHeader('Set-Cookie',cookie('admin','',0));return res.status(200).json({authenticated:false});}
   if(action.startsWith('admin-')){
    if(!admin)throw new ShopError(401,'관리자 로그인이 필요합니다.');
    if(draftService){
     if(action==='admin-draft-products'&&req.method==='GET')return res.status(200).json(await draftService.products(Object.fromEntries(url.searchParams),admin));
     if(action==='admin-drafts'){
      const filters=req.method==='POST'?input.filters:Object.fromEntries(url.searchParams);
      if(!filters||typeof filters!=='object'||Array.isArray(filters))throw new ShopError(400,'초안 조회 조건을 확인해주세요.');
      return res.status(200).json(await draftService.list(filters,admin));
     }
     if(action==='admin-draft'&&req.method==='GET')return res.status(200).json({draft:await draftService.get(url.searchParams.get('id'),admin)});
     if(action==='admin-draft-quote'&&req.method==='GET'){
      const value=await draftService.quote(url.searchParams.get('id'),admin);
      if(Buffer.byteLength(value.body)>4000000)throw new ShopError(413,'견적서 용량을 초과했습니다.');
      if(typeof value.filename!=='string'||!/^[a-zA-Z0-9._-]+$/.test(value.filename))throw new ShopError(503,'견적서 파일명을 확인해주세요.');
      res.setHeader('Content-Type',value.type);res.setHeader('Content-Disposition','attachment; filename="'+value.filename+'"');res.setHeader('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'");return res.status(200).send(value.body);
     }
     if(req.method==='POST'){
      const fn={'admin-draft-update':'update','admin-draft-review':'review','admin-draft-void':'void'}[action];
      if(action==='admin-draft-create')return res.status(201).json({draft:await draftService.create(input,admin)});
      if(fn)return res.status(200).json({draft:await draftService[fn](input.id,input,admin)});
     }
    }
    if(action==='admin-calendar-health'&&req.method==='GET')return res.status(200).json({calendar:repo.calendarHealth?await repo.calendarHealth():null});
    if(action==='admin-orders'&&req.method==='GET')return res.status(200).json(adminService?await adminService.list(Object.fromEntries(url.searchParams)):{orders:await service.adminList()});
    if(action==='admin-orders'&&req.method==='POST'&&adminService){
     if(!input.filters||typeof input.filters!=='object'||Array.isArray(input.filters))throw new ShopError(400,'조회 조건을 확인해주세요.');
     return res.status(200).json(await adminService.list(input.filters));
    }
    if(action==='admin-order'&&req.method==='GET'&&adminService)return res.status(200).json({order:await adminService.detail(url.searchParams.get('id'))});
    if(action==='admin-export'&&adminService){
     if(req.method==='POST'&&(!input.filters||typeof input.filters!=='object'||Array.isArray(input.filters)))throw new ShopError(400,'조회 조건을 확인해주세요.');
     const value=await adminService.export(req.method==='GET'?Object.fromEntries(url.searchParams):{...input.filters,ids:input.ids,format:input.format||'xlsx'});
     if(value.body.length>4000000)throw new ShopError(413,'파일이 큽니다. 조회 기간을 나눠 다운로드해주세요.');
     res.setHeader('Content-Type',value.type);res.setHeader('Content-Disposition','attachment; filename="'+value.filename+'"');return res.status(200).send(value.body);
    }
    if(action==='admin-events'&&req.method==='GET')return res.status(200).json({events:await repo.events(url.searchParams.get('id'))});
    if(req.method==='POST'){
     if(action==='admin-workflow-bulk')return res.status(200).json(await service.workflowBulk(input,admin));
     if(action==='admin-invoice-preview'&&adminService)return res.status(200).json(await adminService.invoicePreview(input,admin));
     if(action==='admin-invoice-apply'&&adminService)return res.status(200).json(await adminService.invoiceApply(input,admin));
     if(action==='admin-workflow')return res.status(200).json({order:await service.workflow(input.id,input,admin)});
     const fn={'admin-approve':'approve','admin-ship':'ship','admin-shipment-update':'updateShipment','admin-case-create':'createCase','admin-case-update':'updateCase','admin-exchange-ship':'exchangeShip','admin-reconcile':'reconcile','admin-document-retry':'retryDocument','admin-rental-pickup':'pickup','admin-rental-return':'rentalReturn','admin-note':'saveNote','admin-cancel-request':'cancelRequest'}[action];
     // The actor is derived exclusively from the verified session, never input.actor.
     if(fn)return res.status(200).json({order:await service[fn](input.id,input,admin)});
    }
    throw new ShopError(404,'요청을 찾을 수 없습니다.');
   }
   const rentalActions=['session','orders','order','rental-create'];
   if(!enabled&&!(rentalEnabled&&rentalActions.includes(action)))throw new ShopError(503,'주문 서비스 연결을 준비 중입니다.');
   if(action==='rental-create'&&!rentalEnabled)throw new ShopError(503,'렌탈 접수 연결을 준비 중입니다.');
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
   if(action==='rental-create'&&req.method==='POST'){await repo.limit('create:'+owner,10,3600);return res.status(201).json({order:await service.createRental(owner,req.headers['idempotency-key'],input)});}
   if(action==='start'&&req.method==='POST')return res.status(200).json(await service.start(input.id,owner,input.quote_version,input.device||'WEB'));
   throw new ShopError(404,'요청을 찾을 수 없습니다.');
  }catch(error){return res.status(error instanceof ShopError?error.status:503).json({error:error instanceof ShopError?error.message:'주문 처리를 확인하고 있습니다. 잠시 후 다시 시도해주세요.'});}
 };
}
module.exports={endpoint};
