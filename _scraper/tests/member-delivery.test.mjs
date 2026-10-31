import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {deliveryData,chooserHTML,applyDelivery,mountDeliveryChooser} from '../../assets/shop/member-delivery.js';
const profile={name:'등록한 회원',phone:'010-1234-5678',postcode:'01234',address:'서울 테스트 주소 123',address_detail:'1층'};
const second={name:'회사 수령인',phone:'02-1234-5678',postcode:'04567',address:'서울 다른 주소 456',address_detail:'3층'};
function formFixture(){
 const fields=Object.fromEntries([...Object.keys(profile),'quantity','tax_address','consent'].map(key=>[key,{value:'manual-'+key,checked:false,disabled:false,events:[],dispatchEvent(e){this.events.push(e.type);},focus(){this.focused=true;}}]));
 const nodes={},styles=[];let root;
 const makeRoot=()=>({className:'',setAttribute(){},set innerHTML(v){this.html=v;},get innerHTML(){return this.html;},querySelector(selector){return nodes[selector]??null;}});
 const doc={createElement(tag){if(tag==='section'){root=makeRoot();return root;}return {setAttribute(){}};},querySelector(){return styles[0]||null;},head:{append(node){styles.push(node);}}};
 const label={before(node){assert.equal(node,root);}};fields.name.closest=()=>label;
 const form={isConnected:true,ownerDocument:doc,elements:{namedItem:name=>fields[name]||null}};
 for(const key of ['profile','clear','recent','status','retry'])nodes['[data-delivery-'+key+']']={value:''};
 return {form,fields,nodes,styles,get root(){return root;}};
}
test('choosing a saved address replaces delivery fields but never consent, tax details or quantity',()=>{
 const {form,fields}=formFixture();const result=applyDelivery(form,profile);assert.equal(result.applied,true);
 for(const key of Object.keys(profile)){assert.equal(fields[key].value,profile[key]);assert.deepEqual(fields[key].events,['input','change']);}
 assert.equal(fields.quantity.value,'manual-quantity');assert.equal(fields.tax_address.value,'manual-tax_address');assert.equal(fields.consent.checked,false);
});
test('incomplete registration only fills known fields and rental selection only fills name and phone',()=>{
 const r=formFixture();applyDelivery(r.form,{name:profile.name},{keepMissing:true});assert.equal(r.fields.phone.value,'manual-phone');assert.equal(r.fields.address.value,'manual-address');
 applyDelivery(r.form,profile,{contactOnly:true});assert.equal(r.fields.phone.value,profile.phone);assert.equal(r.fields.postcode.value,'manual-postcode');assert.equal(r.fields.address.value,'manual-address');
});
test('locked order submissions cannot have any delivery field changed',()=>{
 const r=formFixture();r.fields.phone.disabled=true;assert.equal(applyDelivery(r.form,profile).applied,false);assert.equal(r.fields.name.value,'manual-name');assert.equal(r.fields.phone.value,'manual-phone');
});
test('markup escapes private choices and labels without adding submit buttons',()=>{
 const value=deliveryData({authenticated:true,profile,recent:[{...second,name:'회사 "담당자"',address:'서울 & 다른 주소'}],internal:'do-not-copy'}),html=chooserHTML(value);
 assert.match(html,/회원정보로 입력/);assert.match(html,/최근 배송지/);assert.match(html,/&quot;담당자&quot;/);assert.match(html,/&amp;/);assert.doesNotMatch(html,/do-not-copy|type="submit"/);
 assert.throws(()=>deliveryData({authenticated:false,profile,recent:[]}));assert.equal(deliveryData({authenticated:true,profile:{...profile,address:'<img src=x>'},recent:[]}).profile.address,'');
});
test('member and recent choices fill only on click and change, with no implicit overwrite on load',async()=>{
 const r=formFixture();let request;await mountDeliveryChooser(r.form,{fetcher:async(url,opt)=>{request={url,opt};return {ok:true,status:200,json:async()=>({authenticated:true,profile,recent:[second]})};}});
 assert.equal(r.fields.name.value,'manual-name');assert.equal(request.url,'/api/members?action=delivery');assert.equal(request.opt.credentials,'same-origin');assert.equal(request.opt.cache,'no-store');assert.equal(request.opt.method,undefined);
 r.nodes['[data-delivery-profile]'].onclick();assert.equal(r.fields.name.value,profile.name);assert.equal(r.fields.address.value,profile.address);
 const select=r.nodes['[data-delivery-recent]'];select.value='0';select.onchange();assert.equal(r.fields.name.value,second.name);assert.equal(r.fields.phone.value,second.phone);assert.equal(r.fields.address.value,second.address);
 r.nodes['[data-delivery-clear]'].onclick();assert.equal(r.fields.name.value,'');assert.equal(r.fields.address.value,'');assert.equal(r.fields.name.focused,true);assert.equal(r.fields.consent.checked,false);
 assert.equal(r.styles.length,1);assert.equal(await mountDeliveryChooser(r.form),r.root);
});
test('rental choices ask the server for contact-only data and leave the delivery address alone',async()=>{
 const r=formFixture();let path;await mountDeliveryChooser(r.form,{contactOnly:true,fetcher:async url=>{path=url;return {ok:true,status:200,json:async()=>({authenticated:true,profile:{name:profile.name,phone:profile.phone},recent:[]})};}});
 assert.equal(path,'/api/members?action=delivery&contact=1');r.nodes['[data-delivery-profile]'].onclick();assert.equal(r.fields.name.value,profile.name);assert.equal(r.fields.address.value,'manual-address');
});
test('guest and failed requests keep manual entry available and offer login or retry',async()=>{
 const guest=formFixture();await mountDeliveryChooser(guest.form,{fetcher:async()=>({status:401,ok:false})});assert.match(guest.root.innerHTML,/href="\/account.html"/);assert.equal(guest.fields.name.value,'manual-name');
 const failed=formFixture();let calls=0;await mountDeliveryChooser(failed.form,{fetcher:async()=>{calls++;throw Error('private server details');}});assert.match(failed.root.innerHTML,/data-delivery-retry/);assert.doesNotMatch(failed.root.innerHTML,/private server details/);failed.nodes['[data-delivery-retry]'].onclick();await new Promise(resolve=>setImmediate(resolve));assert.equal(calls,2);assert.equal(failed.fields.name.value,'manual-name');
});
test('late member responses cannot fill or render into a replaced order form',async()=>{
 const r=formFixture();let release;const pending=mountDeliveryChooser(r.form,{fetcher:()=>new Promise(resolve=>release=resolve)});r.form.isConnected=false;release({ok:true,status:200,json:async()=>({authenticated:true,profile,recent:[]})});await pending;assert.equal(r.fields.name.value,'manual-name');assert.equal(r.root.innerHTML,undefined);
});
test('purchase and gift submit controls remain distinct from address picker buttons, and regeneration retains the assets',()=>{
 const code=fs.readFileSync('assets/shop/commerce.js','utf8');assert.equal((code.match(/const button=form\.querySelector\('button\[type=submit\]'\),feedback=form\.querySelector\('\.commerce-feedback'\)/g)||[]).length,2);
 for(const file of ['_scraper/shop_sync.py','_scraper/build_catalog.py']){const source=fs.readFileSync(file,'utf8');assert.ok(source.includes('assets/shop/member-delivery.js'));assert.ok(source.includes('assets/shop/member-delivery.css'));}
 assert.match(fs.readFileSync('assets/shop/rental-content.js','utf8'),/mountDeliveryChooser\(form,\{contactOnly:true\}\)/);
});
