import test from 'node:test';
import assert from 'node:assert/strict';
import {activePromotions,isPromotion,isDiscounted,isConsignmentUsed,catalogSelection} from '../../assets/shop/catalog-tools.js';

const campaign={id:'autumn',type:'supplier_event',start_at:'2026-10-12T00:00:00+09:00',end_at:'2026-11-16T00:00:00+09:00'};
const product={id:'p',name:'카메라',kind:'purchase',price:10000,sale_price:10000,category_ids:[],type_ids:[],promotion_ids:['promotion:autumn'],promotions:[campaign],offers:[{source:'digitalcp'}]};
test('promotion starts inclusively and expires at the exact KST boundary',()=>{
 const start=Date.parse(campaign.start_at),end=Date.parse(campaign.end_at);
 assert.equal(activePromotions(product,start-1).length,0);assert.equal(activePromotions(product,start).length,1);
 assert.equal(activePromotions(product,end-1).length,1);assert.equal(activePromotions(product,end).length,0);
 assert.equal(activePromotions(product,Date.parse('2026-11-15T15:00:00Z')).length,0);
});
test('invalid, unzoned and future periods never show as currently active',()=>{
 for(const change of [{start_at:'2026-10-12'},{end_at:'invalid'},{start_at:'2099-01-01T00:00:00Z',end_at:'2099-02-01T00:00:00Z'}])assert.equal(activePromotions({...product,promotions:[{...campaign,...change}]},Date.parse('2026-10-27T12:00:00+09:00')).length,0);
 assert.equal(activePromotions({...product,kind:'rental'},Date.parse(campaign.start_at)).length,0);
});
test('supplier events and cashback never become a fabricated numeric discount',()=>{
 const clock=Date.now;Date.now=()=>Date.parse('2026-10-27T12:00:00+09:00');
 try{assert.equal(isPromotion(product),true);assert.equal(isDiscounted(product),false);assert.equal(isDiscounted({...product,sale_price:8000}),false);assert.equal(isDiscounted({...product,sale_price:8000,promotions:[{...campaign,type:'price_discount'}]}),true);}finally{Date.now=clock;}
});
test('consignment filters only explicitly marked own purchase stock',()=>{
 const own={...product,name:'[중고] 카메라',promotions:[],offers:[{source:'smartstore'}]};
 assert.equal(isConsignmentUsed(own),true);assert.equal(isConsignmentUsed({...own,kind:'rental'}),false);assert.equal(isConsignmentUsed({...own,offers:[{source:'sunphoto'}]}),false);assert.equal(isConsignmentUsed({...own,name:'[리퍼비시] 카메라'}),false);
 const data={products:[own,product],brands:[],categories:[]};assert.deepEqual(catalogSelection(data,{collection:'used'}).rows.map(p=>p.id),['p']);
});
