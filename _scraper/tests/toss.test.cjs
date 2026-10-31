const {test}=require('node:test');
const assert=require('node:assert/strict');
const {toss,receiptUrl}=require('../../server/commerce/toss.cjs');
const {parseQuery,returnEndpoint}=require('../../server/commerce/toss-return.cjs');
const {popbill}=require('../../server/commerce/popbill.cjs');
const env={SHOP_PAYMENT_MODE:'test',SHOP_TOSS_CLIENT_KEY:'test_ck_fixture',SHOP_TOSS_SECRET_KEY:'test_sk_fixture',SHOP_TOSS_MID:'fixture'};
const row={id:'NS-wire-test',total:11000,lines_json:'[{"name":"카메라"}]'},auth={paymentKey:'fixture_key',orderId:row.id,amount:row.total},customer={name:'테스트',phone:'010-0000-0000'};
const response=value=>({ok:true,json:async()=>value});
const approval={mId:'fixture',orderId:row.id,paymentKey:auth.paymentKey,totalAmount:11000,currency:'KRW',status:'DONE',method:'계좌이체',approvedAt:'2026-10-15T21:00:00+09:00',cashReceipt:{type:'지출증빙',issueNumber:'123456789',amount:11000,receiptUrl:'https://pgweb.tosspayments.com/receipt/fixture'}};
test('Toss keys cannot mix environments; live requires a verified merchant',()=>{
 assert.equal(toss(env).mode,'test');
 for(const change of [{SHOP_TOSS_CLIENT_KEY:'live_ck_fixture'},{SHOP_TOSS_SECRET_KEY:'live_sk_fixture'},{SHOP_TOSS_CLIENT_KEY:'test_gck_wrong_product'},{SHOP_PAYMENT_MODE:'live'}])assert.throws(()=>toss({...env,...change}));
 const live={...env,SHOP_PAYMENT_MODE:'live',SHOP_TOSS_CLIENT_KEY:'live_ck_fixture',SHOP_TOSS_SECRET_KEY:'live_sk_fixture'};
 assert.throws(()=>toss(live));assert.equal(toss({...live,SHOP_TOSS_LIVE_VERIFIED:'true'}).mode,'live');
});
test('payment-window keys use matching families, private API auth and the same ownership checks',async()=>{
 const modern={...env,SHOP_TOSS_CLIENT_KEY:'test_gck_fixture',SHOP_TOSS_SECRET_KEY:'test_gsk_fixture'};
 const calls=[],adapter=toss(modern,async(url,options)=>{calls.push({url,options});return response(approval);});
 const prepared=adapter.prepare(row,customer,'signed');assert.equal(prepared.clientKey,modern.SHOP_TOSS_CLIENT_KEY);assert.equal(prepared.amount,row.total);assert.ok(!JSON.stringify(prepared).includes(modern.SHOP_TOSS_SECRET_KEY));
 assert.throws(()=>adapter.prepare(row,{...customer,evidence:{kind:'tax_invoice'}},'signed'));
 assert.equal((await adapter.approve(auth,row)).method,'BANK');assert.equal(calls[0].options.headers.Authorization,'Basic '+Buffer.from(modern.SHOP_TOSS_SECRET_KEY+':').toString('base64'));
 for(const change of [{SHOP_TOSS_SECRET_KEY:'test_sk_fixture'},{SHOP_TOSS_SECRET_KEY:'live_gsk_fixture'},{SHOP_TOSS_CLIENT_KEY:'test_ck_fixture'}])assert.throws(()=>toss({...modern,...change}));
 await assert.rejects(toss(modern,async()=>response({...approval,totalAmount:1})).approve(auth,row));
});
test('server quote prepares card or transfer and excludes duplicate invoice evidence',()=>{
 const adapter=toss(env),card=adapter.prepare(row,customer,'signed'),cash=adapter.prepare(row,{...customer,evidence:{kind:'cash_receipt'}},'signed'),tax=adapter.prepare(row,{...customer,evidence:{kind:'tax_invoice'}},'signed');
 assert.deepEqual(card.request.amount,{currency:'KRW',value:11000});assert.equal(card.request.method,'CARD');assert.equal(cash.request.method,'TRANSFER');assert.equal(tax.request.transfer.cashReceipt.type,'미발행');assert.match(card.request.successUrl,/^https:\/\/shop.nadaun.co\/api\/toss-return\?token=signed$/);assert.ok(!JSON.stringify(card).includes(env.SHOP_TOSS_SECRET_KEY));
});
test('confirm binds order and amount, sends private Basic auth and a stable idempotency key',async()=>{
 const calls=[],adapter=toss(env,async(url,options)=>{calls.push({url,options});return response(approval);});
 const result=await adapter.approve(auth,row);await adapter.approve(auth,row);
 assert.equal(calls[0].url,'https://api.tosspayments.com/v1/payments/confirm');assert.equal(calls[0].options.redirect,'error');assert.deepEqual(JSON.parse(calls[0].options.body),auth);assert.equal(calls[0].options.headers.Authorization,'Basic '+Buffer.from(env.SHOP_TOSS_SECRET_KEY+':').toString('base64'));
 assert.equal(calls[0].options.headers['Idempotency-Key'],calls[1].options.headers['Idempotency-Key']);assert.equal(result.cashReceipt.purpose,'business');assert.equal(result.cashReceipt.issued,true);assert.equal(result.method,'BANK');
});
test('foreign identity, amount, currency, merchant or incomplete approval is rejected',async()=>{
 for(const change of [{orderId:'foreign'},{paymentKey:'foreign'},{totalAmount:1},{currency:'USD'},{mId:'foreign'},{status:'WAITING_FOR_DEPOSIT'}])await assert.rejects(toss(env,async()=>response({...approval,...change})).approve(auth,row));
 const adapter=toss(env);for(const change of [{orderId:'foreign'},{paymentKey:'bad/key'},{amount:'1'},{amount:'11000.0'}])assert.throws(()=>adapter.validateAuthentication({orderId:row.id,paymentKey:auth.paymentKey,amount:'11000',...change},row));
});
test('compensation queries ownership first and only cancels the matching completed payment',async()=>{
 const calls=[];const adapter=toss(env,async(url,options)=>{calls.push({url,options});return response({...approval,status:options.method==='POST'?'CANCELED':'DONE'});});
 assert.equal((await adapter.netCancel(auth,row)).canceled,true);assert.equal(calls[0].options.method,'GET');assert.match(calls[1].url,/fixture_key\/cancel$/);assert.match(calls[1].options.headers['Idempotency-Key'],/^nadaun-compensate-/);
 let count=0;await assert.rejects(toss(env,async()=>{count++;return response({...approval,orderId:'foreign'});}).netCancel(auth,row));assert.equal(count,1);
 count=0;assert.equal((await toss(env,async()=>{count++;return response({...approval,status:'CANCELED'});}).netCancel(auth,row)).canceled,true);assert.equal(count,1);
});
test('network failures and provider secrets are never reflected to clients',async()=>{
 for(const fetcher of [async()=>{throw Error('private secret');},async()=>({ok:false,json:async()=>({message:'private secret'})})])await assert.rejects(toss(env,fetcher).approve(auth,row),e=>!e.message.includes('private secret'));
});
test('receipt URLs reject lookalike hosts, credentials, javascript and plaintext links',()=>{
 assert.equal(receiptUrl('https://dashboard.tosspayments.com/receipt/fixture'),'https://dashboard.tosspayments.com/receipt/fixture');
 for(const url of ['https://dashboard.tosspayments.com.evil.invalid/','https://x@dashboard.tosspayments.com/','http://dashboard.tosspayments.com/','javascript:alert(1)'])assert.equal(receiptUrl(url),null);
});
test('callback rejects duplicate/oversized query and redirects without reflecting secrets',async()=>{
 assert.equal(parseQuery({url:'/api/toss-return?token=signed'}).token,'signed');assert.throws(()=>parseQuery({url:'/api/toss-return?token=a&token=b'}));assert.throws(()=>parseQuery({url:'/api/toss-return?token='+'x'.repeat(5000)}));
 const res={headers:{},setHeader(k,v){this.headers[k]=v;},status(v){this.code=v;return this;},end(v){this.body=v;}};
 await returnEndpoint(()=>({acceptReturn:async()=>{throw Error('private');}}))({method:'GET',url:'/api/toss-return?token=secret'},res);assert.equal(res.code,303);assert.equal(res.headers.Location,'/orders.html?result=check');assert.equal(res.body,undefined);assert.equal(res.headers['Referrer-Policy'],'no-referrer');
 await returnEndpoint(()=>{throw Error('must not call');})({method:'POST',url:'/api/toss-return'},res);assert.equal(res.code,405);
});
const taxEnv={...env,SHOP_TAX_INVOICE_ENABLED:'true',SHOP_TAX_INVOICE_PROVIDER:'popbill',SHOP_POPBILL_MODE:'test',SHOP_POPBILL_LINK_ID:'fixture',SHOP_POPBILL_SECRET_KEY:'fixture-only',SHOP_POPBILL_USER_ID:'fixture',SHOP_SELLER_CORP_NUM:'1234567891',SHOP_SELLER_CORP_NAME:'공급자',SHOP_SELLER_CEO_NAME:'대표',SHOP_TAX_PROFILE:'taxable_vat_included'};
const buyer={corp_num:'1234567891',corp_name:'구매자',ceo_name:'고객',email:'test@example.invalid',address:'테스트 주소',biz_type:'도소매',biz_class:'촬영장비'};
test('optional invoice adapter cannot silently enable or mix test/live environments',()=>{assert.equal(popbill({}),null);assert.throws(()=>popbill({...taxEnv,SHOP_POPBILL_MODE:'live'},{}));assert.throws(()=>popbill({...taxEnv,SHOP_TAX_PROFILE:''},{}));});
test('tax invoice uses verified payment total/date, exact buyer and stable seller document key',async()=>{
 let sent;const sdk={registIssue(...args){sent=args[1];args.at(-2)({code:1,ntsConfirmNum:'202610081234567890123456'});}};const adapter=popbill(taxEnv,sdk),result=await adapter.issue('NSfixed',row,buyer,Date.parse('2026-10-07T16:00:00Z'));assert.equal(sent.writeDate,'20261008');assert.equal(sent.purposeType,'영수');assert.equal(sent.supplyCostTotal,'10000');assert.equal(sent.taxTotal,'1000');assert.equal(sent.totalAmount,'11000');assert.equal(sent.invoicerMgtKey,'NSfixed');assert.equal(result.nts_status,'pending');
});
test('invoice lookup validates full document ownership/total and distinguishes NTS acceptance',async()=>{
 const detail={invoicerMgtKey:'NSfixed',invoicerCorpNum:'1234567891',invoiceeCorpNum:buyer.corp_num,totalAmount:'11000',taxType:'과세'};const info={stateCode:304,ntsconfirmNum:'202610081234567890123456'};
 const sdk={checkMgtKeyInUse(...a){a.at(-2)(true);},getDetailInfo(...a){a.at(-2)(detail);},getInfo(...a){a.at(-2)(info);}};const adapter=popbill(taxEnv,sdk);assert.equal((await adapter.lookup('NSfixed',row,buyer)).nts_status,'accepted');detail.totalAmount='1';await assert.rejects(adapter.lookup('NSfixed',row,buyer));detail.totalAmount='11000';info.stateCode=600;await assert.rejects(adapter.lookup('NSfixed',row,buyer));
});
test('document recovery endpoint rejects unauthenticated requests and stays inert before orders open',async()=>{
 const handler=require('../../api/commerce-jobs.js'),before={secret:process.env.SHOP_JOBS_SECRET,enabled:process.env.SHOP_ORDERS_ENABLED};
 const response=()=>({status(v){this.code=v;return this;},json(value){this.value=value;return this;},setHeader(){}});
 try{process.env.SHOP_JOBS_SECRET='f'.repeat(64);process.env.SHOP_ORDERS_ENABLED='false';let res=response();await handler({method:'POST',headers:{}},res);assert.equal(res.code,401);
 res=response();await handler({method:'POST',headers:{authorization:'Bearer '+'f'.repeat(64)}},res);assert.equal(res.code,200);assert.deepEqual(res.value,{state:'disabled',processed:0});
 res=response();await handler({method:'GET',headers:{authorization:'Bearer '+'f'.repeat(64)}},res);assert.equal(res.code,401);
 }finally{for(const [key,value] of [['SHOP_JOBS_SECRET',before.secret],['SHOP_ORDERS_ENABLED',before.enabled]])if(value===undefined)delete process.env[key];else process.env[key]=value;}
});
