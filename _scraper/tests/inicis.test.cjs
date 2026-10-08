const {test}=require('node:test');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const {inicis}=require('../../server/commerce/inicis.cjs');
const {parseBody,returnEndpoint}=require('../../server/commerce/inicis-return.cjs');
const {popbill}=require('../../server/commerce/popbill.cjs');
const env={SHOP_PAYMENT_MODE:'test',SHOP_INICIS_MID:'INIpayTest',SHOP_INICIS_HASH_KEY:'fixture-hash-key-123',SHOP_INICIS_API_KEY:'fixture-api-key-123',SHOP_INICIS_CLIENT_IP:'192.0.2.5'};
const row={id:'NS-wire-test',total:11000,lines_json:'[{"name":"카메라"}]'},auth={P_AUTH_TID:'authentication_fixture_123',P_IDCNAME:'fc'},customer={name:'테스트',phone:'010-0000-0000'};
const response=value=>({ok:true,text:async()=>JSON.stringify(value)});
const approval={P_STATUS:'00',P_MID:'INIpayTest',P_OID:row.id,P_AMT:'11000',P_AUTH_TID:auth.P_AUTH_TID,P_APPL_TID:'approval_fixture_123',P_TYPE:'BANK',P_CSHR_CODE:'0000',P_CSHR_AMT:'11000',P_CSHR_TYPE:'1',P_CSHR_AUTH_NO:'123456789',P_CSHR_DT:'20261008120000'};
test('only known test MID is allowed in test mode; live requires explicit verified activation',()=>{
 assert.throws(()=>inicis({...env,SHOP_INICIS_MID:'LIVE123456'}));assert.throws(()=>inicis({...env,SHOP_PAYMENT_MODE:'live'}));assert.throws(()=>inicis({...env,SHOP_PAYMENT_MODE:'live',SHOP_INICIS_MID:'LIVE123456'}));assert.equal(inicis({...env,SHOP_PAYMENT_MODE:'live',SHOP_INICIS_MID:'LIVE123456',SHOP_INICIS_LIVE_VERIFIED:'true'}).mode,'live');
});
test('PRO digest matches official field order and evidence chooses exclusive payment methods',()=>{
 const adapter=inicis(env,undefined,()=>123456789),card=adapter.prepare(row,customer,'token');assert.equal(card.fields.P_CHKFAKE,crypto.createHash('sha512').update('11000NS-wire-test123456789'+env.SHOP_INICIS_HASH_KEY).digest('base64'));assert.equal(card.fields.P_PAY_TYPE,'CARD');
 const cash=adapter.prepare(row,{...customer,evidence:{kind:'cash_receipt'}},'token','MOBILE');assert.equal(cash.fields.P_PAY_TYPE,'BANK');assert.equal(cash.fields.P_DEVICE_TYPE,'MOBILE');assert.equal(JSON.parse(cash.fields.P_RESERVED).bank_receipt,undefined);
 const tax=adapter.prepare(row,{...customer,evidence:{kind:'tax_invoice',email:'test@example.invalid'}},'token');assert.equal(tax.fields.P_PAY_TYPE,'BANK');assert.equal(JSON.parse(tax.fields.P_RESERVED).bank_receipt,'N');
});
test('approval uses derived allowlisted host, bounded form request and verified receipt response',async()=>{
 let request;const adapter=inicis(env,async(url,options)=>{request={url,options};return response(approval);});const result=await adapter.approve(auth,row);assert.equal(request.url,'https://fcpaypro.inicis.com/payment/v1/rest/payAppl.ini');assert.equal(request.options.redirect,'error');assert.equal(new URLSearchParams(request.options.body).get('P_AMT'),'11000');assert.equal(result.cashReceipt.purpose,'business');assert.equal(result.cashReceipt.issued,true);assert.equal(result.cashReceipt.amount,11000);
 await assert.rejects(adapter.approve({...auth,P_IDCNAME:'attacker.invalid'},row));
});
test('wrong amount, MID, order, auth token, approval token or method rejects successful-looking approval',async()=>{
 for(const change of [{P_AMT:'1'},{P_MID:'foreign'},{P_OID:'foreign'},{P_AUTH_TID:'foreign'},{P_APPL_TID:'bad'},{P_TYPE:'VBANK'}])await assert.rejects(inicis(env,async()=>response({...approval,...change})).approve(auth,row));
});
test('inquiry signs exact JSON data and treats IN_PROGRESS receipt as unconfirmed',async()=>{
 let request;const data={resultCode:'SUCCESS',mid:'INIpayTest',oid:row.id,tid:'approval_fixture_123',price:'11000',transactionStatus:'APPROVAL',paymethod:'DirectBank',cashReceiptInfo:{issueStatus:'APPROVAL',approvedResultCode:'IN_PROGRESS',approvedNumber:'123456789'}};
 const adapter=inicis(env,async(url,options)=>{request=JSON.parse(options.body);return response(data);},()=>1791417600000);const result=await adapter.get(data.tid);assert.equal(request.hashData,crypto.createHash('sha512').update(env.SHOP_INICIS_API_KEY+env.SHOP_INICIS_MID+'inquiry'+request.timestamp+JSON.stringify(request.data)).digest('hex'));assert.equal(result.cashReceipt.issued,false);assert.equal(result.cashReceipt.present,true);
 data.cashReceiptInfo.approvedResultCode='COMPLETED';assert.equal((await adapter.get(data.tid)).cashReceipt.issued,true);data.transactionStatus='CANCEL';assert.equal((await adapter.get(data.tid)).status,'CANCELED');
});
test('malformed IP and unexpected inquiry identity or status stay blocked',async()=>{
 await assert.rejects(inicis({...env,SHOP_INICIS_CLIENT_IP:'999.2.3.4'},async()=>{throw Error('should not fetch');}).get('approval_fixture_123'));
 for(const data of [{resultCode:'00'},{resultCode:'SUCCESS',mid:'other'},{resultCode:'SUCCESS',mid:'INIpayTest',tid:'approval_fixture_123',transactionStatus:'UNKNOWN'}])await assert.rejects(inicis(env,async()=>response(data)).get('approval_fixture_123'));
});
test('callback parser rejects duplicated fields, wrong content type and oversized body',()=>{
 const req={headers:{'content-type':'application/x-www-form-urlencoded'},body:'P_STATUS=00&P_NOTI=signed'};assert.equal(parseBody(req).P_NOTI,'signed');assert.throws(()=>parseBody({...req,body:'P_STATUS=00&P_STATUS=01'}));assert.throws(()=>parseBody({...req,headers:{'content-type':'application/json'}}));assert.throws(()=>parseBody({...req,body:'x'.repeat(17000)}));
});
test('callback only redirects to fixed order path, without reflecting secrets or provider errors',async()=>{
 const res={headers:{},statusCode:200,setHeader(k,v){this.headers[k]=v;},status(v){this.statusCode=v;return this;},end(v){this.body=v;}};
 await returnEndpoint(()=>({acceptReturn:async()=>{throw Error('private provider detail');}}))({method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body:'P_NOTI=secret'},res);assert.match(res.body,/\/orders.html\?result=check/);assert.ok(!res.body.includes('secret'));assert.ok(!res.body.includes('private provider'));assert.match(res.headers['Content-Security-Policy'],/nonce-/);
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
