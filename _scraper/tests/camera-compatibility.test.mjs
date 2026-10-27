import test from 'node:test';
import assert from 'node:assert/strict';
import {compatibleAccessories,compatibilitySection} from '../../assets/shop/compatibility.js';
import {catalogSelection} from '../../assets/shop/catalog-tools.js';
const camera={id:'nikon-1',kind:'purchase',brand_id:'nikon',camera_model_ids:['nikon-zr'],type_ids:['camera'],category_ids:[]};
const accessory=(id,brand,models=['nikon-zr'])=>({id,kind:'purchase',brand_id:brand,compatible_camera_model_ids:models,type_ids:['cage'],category_ids:[],name:brand+' cage'});
const data={products:[camera,accessory('smallrig-1','smallrig'),accessory('tilta-1','tilta'),accessory('sony-1','smallrig',['sony-fx3']),{...accessory('rental-1','tilta'),kind:'rental'}],brands:[],categories:[],camera_models:[{id:'nikon-zr',name:'Nikon ZR',accessory_product_ids:['smallrig-1','tilta-1']}]};
test('Nikon camera shows different accessory makers and excludes other bodies and rental',()=>{
 assert.deepEqual(compatibleAccessories(camera,data).map(p=>p.id),['smallrig-1','tilta-1']);
 const html=compatibilitySection(camera,data,p=>'<article>'+p.id+'</article>');
 assert.match(html,/smallrig-1/);assert.match(html,/tilta-1/);assert.doesNotMatch(html,/sony-1/);
 assert.match(html,/camera=nikon-zr/);
});
test('camera filter keeps matching accessories and meaningful category counts',()=>{
 const selected=catalogSelection(data,{camera:'nikon-zr'});
 assert.deepEqual(selected.rows.map(p=>p.id),['smallrig-1','tilta-1']);assert.equal(selected.typeCounts.get('cage'),2);
 assert.equal(catalogSelection(data,{camera:'nikon-zr',brand:'tilta'}).rows.length,1);
 assert.equal(catalogSelection(data,{camera:'missing-camera'}).rows.length,0);
});
test('same option family does not recommend itself and model labels are escaped',()=>{
 const current={...accessory('smallrig-1','smallrig'),listing_id:'family-1'};
 const rows={...data,products:[current,{...accessory('smallrig-2','smallrig'),listing_id:'family-1'},accessory('tilta-1','tilta')],camera_models:[{id:'nikon-zr',name:'<img onerror=alert(1)>',accessory_product_ids:['tilta-1']}]};
 assert.deepEqual(compatibleAccessories(current,rows).map(p=>p.id),['tilta-1']);
 assert.doesNotMatch(compatibilitySection(current,rows,()=>''),/<img onerror/);
});
