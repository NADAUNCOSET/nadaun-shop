const {test}=require('node:test'),assert=require('node:assert/strict');
const {reviewEndpoint}=require('../../server/commerce/toss-review.cjs');
const env={SHOP_SESSION_KEY:'a'.repeat(64),SHOP_TOSS_TEST_CLIENT_KEY:'test_ck_fixture',SHOP_TOSS_TEST_SECRET_KEY:'test_sk_fixture',SHOP_TOSS_TEST_MID:'fixture'};
const catalog={products:[{id:'purchase-one',name:'카메라 구매',kind:'purchase',status:'sale',price:20000},{id:'rental-one',name:'메모리 대여',kind:'rental',status:'sale',price:10000}]};
function fixture(changes={},transform=value=>value){
 let now=Date.now(),state='DONE',intent,calls=[];
 const fetcher=async(url,opt)=>{calls.push({url,opt});let payment={mId:'fixture',paymentKey:'test_payment',orderId:intent.orderId,totalAmount:intent.amount,currency:'KRW',status:state,...(intent.request.method==='CARD'?{card:{approveNo:'12345'}}:{method:'계좌이체',cashReceipt:{type:'소득공제',issueNumber:'123456',amount:intent.amount}})};
  if(url.endsWith('/cancel'))state='CANCELED';payment.status=state;return {ok:true,json:async()=>transform(payment)};};
 const handler=reviewEndpoint({env:{...env,...changes},catalog,fetcher,clock:()=>now});
 async function call(action,{method='GET',body,url='',origin='https://shop.nadaun.co'}={}){const res={headers:{},setHeader(k,v){this.headers[k]=v;},status(v){this.code=v;return this;},json(v){this.value=v;return this;},send(v){this.value=v;return this;}};await handler({url:'/api/toss-review?action='+action+url,method,body,headers:{origin,'content-type':'application/json'}},res);return res;}
 return {call,calls,setIntent(v){intent=v;},expire(){now+=16*60000;}};
}
test('review never accepts live keys or exposes secrets; ordinary ordering stays separate',async()=>{
 for(const change of [{SHOP_TOSS_TEST_CLIENT_KEY:''},{SHOP_TOSS_TEST_CLIENT_KEY:'live_ck_wrong'},{SHOP_TOSS_TEST_SECRET_KEY:'live_sk_wrong'}]){const f=fixture(change);assert.equal((await f.call('config')).value.configured,false);assert.equal((await f.call('prepare',{method:'POST',body:{id:'purchase-one',method:'CARD'}})).code,503);assert.equal(f.calls.length,0);}
 const f=fixture();assert.equal((await f.call('config')).value.configured,true);assert.ok(!JSON.stringify((await f.call('config')).value).includes(env.SHOP_TOSS_TEST_SECRET_KEY));
});
test('server owns product price; review requests reject foreign origin, malformed bodies and unknown items',async()=>{
 const f=fixture();assert.equal((await f.call('prepare',{method:'POST',origin:'https://other.invalid',body:{}})).code,403);
 for(const body of [[],{id:'missing',method:'CARD'},{id:'purchase-one',method:'OTHER'}])assert.equal((await f.call('prepare',{method:'POST',body})).code,400);
 for(const id of ['purchase-one','rental-one']){const res=await f.call('prepare',{method:'POST',body:{id,method:'CARD',amount:1}});assert.equal(res.code,200);assert.equal(res.value.amount,id==='purchase-one'?20000:10000);assert.equal(res.value.mode,'test');assert.ok(!JSON.stringify(res.value).includes(env.SHOP_TOSS_TEST_SECRET_KEY));assert.match(res.value.request.successUrl,/\/api\/toss-review\?action=return&token=/);assert.equal(res.value.request.customerMobilePhone,undefined);}
});
test('expired or duplicate callback parameters cannot reach Toss',async()=>{
 const f=fixture(),v=(await f.call('prepare',{method:'POST',body:{id:'purchase-one',method:'CARD'}})).value;const token=new URL(v.request.successUrl).searchParams.get('token');
 const url='&token='+encodeURIComponent(token)+'&paymentKey=test_payment&orderId='+v.orderId+'&amount=20000';
 assert.equal((await f.call('return',{url:url+'&amount=1'})).code,400);f.expire();assert.equal((await f.call('return',{url})).code,400);assert.equal(f.calls.length,0);
});
test('merchant test approval and verified idempotent cancellation do not need an operational database',async()=>{
 const f=fixture(),v=(await f.call('prepare',{method:'POST',body:{id:'purchase-one',method:'CARD'}})).value;f.setIntent(v);const token=new URL(v.request.successUrl).searchParams.get('token');
 let res=await f.call('return',{url:'&token='+encodeURIComponent(token)+'&paymentKey=test_payment&orderId='+v.orderId+'&amount=1'});assert.equal(res.code,400);assert.equal(f.calls.length,0);
 res=await f.call('return',{url:'&token='+encodeURIComponent(token)+'&paymentKey=test_payment&orderId='+v.orderId+'&amount=20000'});assert.equal(res.code,200);assert.match(res.value,/테스트 결제 승인 완료/);const cancel=res.value.match(/name="token" value="([^"]+)"/)[1];
 res=await f.call('cancel',{method:'POST',body:{token:cancel}});assert.equal(res.code,200);assert.match(res.value,/테스트 결제 취소 완료/);
 res=await f.call('cancel',{method:'POST',body:{token:cancel}});assert.equal(res.code,200);assert.equal(f.calls.filter(c=>c.url.endsWith('/cancel')).length,1);assert.ok(f.calls[0].opt.headers['Idempotency-Key']);
});

test('transfer test approval keeps the requested amount and method',async()=>{
 const f=fixture(),v=(await f.call('prepare',{method:'POST',body:{id:'rental-one',method:'TRANSFER'}})).value;f.setIntent(v);const token=new URL(v.request.successUrl).searchParams.get('token');
 const res=await f.call('return',{url:'&token='+encodeURIComponent(token)+'&paymentKey=test_payment&orderId='+v.orderId+'&amount=10000'});assert.equal(res.code,200);assert.match(res.value,/테스트 결제 승인 완료/);
});
test('foreign or changed provider amounts cannot produce a test success',async()=>{
 for(const change of [{totalAmount:1},{orderId:'another-order'},{mId:'another-merchant'}]){const f=fixture({},p=>({...p,...change})),v=(await f.call('prepare',{method:'POST',body:{id:'purchase-one',method:'CARD'}})).value;f.setIntent(v);const token=new URL(v.request.successUrl).searchParams.get('token');
  const res=await f.call('return',{url:'&token='+encodeURIComponent(token)+'&paymentKey=test_payment&orderId='+v.orderId+'&amount=20000'});assert.equal(res.code,502);assert.ok(!JSON.stringify(res.value).includes(env.SHOP_TOSS_TEST_SECRET_KEY));}
});
test('cancellation verifies transaction ownership before sending a cancel',async()=>{
 let foreign=false;const f=fixture({},p=>foreign?{...p,orderId:'another-order'}:p),v=(await f.call('prepare',{method:'POST',body:{id:'purchase-one',method:'CARD'}})).value;f.setIntent(v);const token=new URL(v.request.successUrl).searchParams.get('token');
 const approved=await f.call('return',{url:'&token='+encodeURIComponent(token)+'&paymentKey=test_payment&orderId='+v.orderId+'&amount=20000'}),cancel=approved.value.match(/name="token" value="([^"]+)"/)[1];foreign=true;
 assert.equal((await f.call('cancel',{method:'POST',body:{token:cancel}})).code,502);assert.equal(f.calls.filter(c=>c.url.endsWith('/cancel')).length,0);
});
