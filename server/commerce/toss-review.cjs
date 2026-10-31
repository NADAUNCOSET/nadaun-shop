'use strict';
// Merchant test keys only. This flow never opens or writes the operational DB.
const crypto=require('node:crypto');
const {ShopError,sessions}=require('./security.cjs');
const {toss,keyFamily,matchPayment}=require('./toss.cjs');
const ORIGIN='https://shop.nadaun.co';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function reviewEndpoint({env,catalog,fetcher=fetch,clock=()=>Date.now()}){
 const client=env.SHOP_TOSS_TEST_CLIENT_KEY,secret=env.SHOP_TOSS_TEST_SECRET_KEY;
 const ready=!!keyFamily('test',client,secret)&&/^[a-f0-9]{64}$/i.test(env.SHOP_SESSION_KEY||'');
 const adapter=ready?toss({...env,SHOP_PAYMENT_MODE:'test',SHOP_TOSS_CLIENT_KEY:client,SHOP_TOSS_SECRET_KEY:secret,SHOP_TOSS_MID:env.SHOP_TOSS_TEST_MID||'',SHOP_TOSS_LIVE_VERIFIED:'false'},fetcher):null;
 const signed=ready?sessions(env.SHOP_SESSION_KEY,clock):null;
 const options=['purchase','rental'].map(kind=>(catalog.products||[]).find(p=>p.kind===kind&&p.status==='sale'&&Number.isSafeInteger(p.sale_price??p.price)&&(p.sale_price??p.price)>0&&(p.sale_price??p.price)<=100000000)).filter(Boolean).map(p=>({id:p.id,name:p.name,kind:p.kind,amount:p.sale_price??p.price}));
 const limits=new Map();
 function limit(req){const ip=String(req.headers['x-forwarded-for']||'unknown').split(',')[0].trim(),now=clock();for(const [key,row] of limits)if(now-row.since>600000)limits.delete(key);const row=limits.get(ip)||{since:now,count:0};if(limits.size>=512&&!limits.has(ip)||++row.count>30)throw new ShopError(429,'잠시 후 다시 테스트해주세요.');limits.set(ip,row);}
 function read(token,role){let value;try{value=JSON.parse(signed.read(token,role));}catch{}if(!value||!/^NDTEST_[a-f0-9]{24}$/.test(value.id)||!Number.isSafeInteger(value.amount)||value.amount<1||value.amount>100000000||!['CARD','TRANSFER'].includes(value.method))throw new ShopError(400,'테스트 요청이 만료되었거나 올바르지 않습니다. 다시 시작해주세요.');return value;}
 const row=v=>({id:v.id,total:v.amount,lines_json:JSON.stringify([{name:v.name}])});
 function html(res,title,body){res.setHeader('Content-Type','text/html; charset=utf-8');res.setHeader('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; font-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'");return res.status(200).send('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>'+esc(title)+' | 나다운 스페이스</title><style>@font-face{font-family:Pretendard;src:url(/assets/shop/fonts/PretendardVariable.woff2) format("woff2");font-weight:100 900;font-display:swap}body{margin:0;background:#fafaf8;color:#202020;font:16px/1.7 Pretendard,system-ui,sans-serif}main{max-width:720px;margin:10vh auto;padding:32px}h1{font-size:32px;line-height:1.3}dl{display:grid;grid-template-columns:100px 1fr;gap:8px}dd{margin:0;overflow-wrap:anywhere}button,a{font:inherit}button{padding:12px 20px;border:0;background:#222;color:white;cursor:pointer}a{color:inherit}</style><main><p>NADAUN SHOP · TEST</p><h1>'+esc(title)+'</h1><p>실제 대금이 청구되지 않는 토스페이먼츠 테스트입니다. 상품 주문이나 렌탈 예약이 생성되지 않습니다.</p>'+body+'<p><a href="/payment-test.html">테스트 화면으로 돌아가기 →</a></p></main></html>');}
 return async function(req,res){
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex, nofollow');res.setHeader('Referrer-Policy','no-referrer');
  try{
   const url=new URL(req.url,ORIGIN),action=url.searchParams.get('action')||'config';
   if(!['GET','POST'].includes(req.method))throw new ShopError(405,'허용되지 않은 요청입니다.');
   if(req.method==='GET'&&action==='config')return res.status(200).json({configured:ready,mode:'test',products:options});
   if(!ready)throw new ShopError(503,'토스 테스트 상점 연결을 준비하고 있습니다.');
   if(req.method==='POST'&&req.headers.origin!==ORIGIN)throw new ShopError(403,'나다운 테스트 화면에서 다시 시작해주세요.');
   limit(req);let input=req.body||{};
   if(typeof input==='string'){if(Buffer.byteLength(input)>4096)throw new ShopError(413,'요청 크기를 확인해주세요.');try{input=req.headers['content-type']?.startsWith('application/x-www-form-urlencoded')?Object.fromEntries(new URLSearchParams(input)):JSON.parse(input);}catch{throw new ShopError(400,'요청 형식을 확인해주세요.');}}
   if(!input||typeof input!=='object'||Array.isArray(input)||Buffer.byteLength(JSON.stringify(input))>4096)throw new ShopError(400,'요청 형식을 확인해주세요.');
   if(req.method==='POST'&&action==='prepare'){
    const product=options.find(p=>p.id===input.id);if(!product||!['CARD','TRANSFER'].includes(input.method))throw new ShopError(400,'테스트 상품과 결제수단을 확인해주세요.');
    const intent={id:'NDTEST_'+crypto.randomBytes(12).toString('hex'),amount:product.amount,name:product.name,kind:product.kind,method:input.method};
    const token=signed.issue(JSON.stringify(intent),'toss-review',900),value=adapter.prepare(row(intent),{name:'나다운 연동 테스트',phone:'',evidence:{kind:input.method==='CARD'?'card_receipt':'cash_receipt'}},token);
    value.request.successUrl=ORIGIN+'/api/toss-review?action=return&token='+encodeURIComponent(token);value.request.failUrl=ORIGIN+'/payment-test.html?result=closed';delete value.request.customerMobilePhone;
    return res.status(200).json({...value,kind:product.kind});
   }
   if(req.method==='GET'&&action==='return'){
    for(const key of ['token','paymentKey','orderId','amount'])if(url.searchParams.getAll(key).length!==1)throw new ShopError(400,'테스트 응답 정보를 확인해주세요.');
    const intent=read(url.searchParams.get('token'),'toss-review'),order=row(intent),auth=adapter.validateAuthentication(Object.fromEntries(url.searchParams),order);
    const payment=await adapter.approve(auth,order);if(payment.method!==(intent.method==='CARD'?'CARD':'BANK'))throw new ShopError(502,'테스트 결제수단을 확인해주세요.');
    const token=signed.issue(JSON.stringify({...intent,paymentKey:payment.paymentKey}),'toss-review-cancel',900);
    return html(res,'테스트 결제 승인 완료','<dl><dt>상품</dt><dd>'+esc(intent.name)+'</dd><dt>테스트 금액</dt><dd>'+intent.amount.toLocaleString('ko-KR')+'원</dd><dt>주문번호</dt><dd>'+esc(intent.id)+'</dd></dl><form method="post" action="/api/toss-review?action=cancel"><input type="hidden" name="token" value="'+esc(token)+'"><button>테스트 결제 취소 확인</button></form>');
   }
   if(req.method==='POST'&&action==='cancel'){
    const intent=read(input.token,'toss-review-cancel'),order=row(intent),auth={paymentKey:intent.paymentKey,orderId:intent.id,amount:intent.amount};
    let payment=await adapter.get(intent.paymentKey);matchPayment(payment,{...order,payment_key:intent.paymentKey});
    if(payment.status!=='CANCELED'){
     if(payment.status!=='DONE')throw new ShopError(409,'테스트 결제 상태를 확인해주세요.');
     const response=await fetcher('https://api.tosspayments.com/v1/payments/'+encodeURIComponent(intent.paymentKey)+'/cancel',{method:'POST',redirect:'error',headers:{Authorization:'Basic '+Buffer.from(secret+':').toString('base64'),'Content-Type':'application/json','Idempotency-Key':'ndtest-cancel-'+crypto.createHash('sha256').update(intent.id).digest('hex').slice(0,40)},body:JSON.stringify({cancelReason:'나다운 연동 테스트 결제 취소'}),signal:AbortSignal.timeout(12000)});
     if(!response.ok)throw new ShopError(502,'테스트 취소 결과를 확인해주세요.');
     payment=await adapter.get(intent.paymentKey);matchPayment(payment,{...order,payment_key:intent.paymentKey});if(payment.status!=='CANCELED')throw new ShopError(502,'테스트 취소 결과를 확인해주세요.');
    }
    return html(res,'테스트 결제 취소 완료','<p>테스트 주문번호 '+esc(intent.id)+'의 취소 상태를 토스페이먼츠에서 확인했습니다.</p>');
   }
   throw new ShopError(404,'테스트 경로를 확인해주세요.');
  }catch(error){return res.status(error instanceof ShopError?error.status:503).json({error:error instanceof ShopError?error.message:'테스트 연결을 확인하지 못했습니다. 잠시 후 다시 시도해주세요.'});}
 };
}
module.exports={reviewEndpoint};
