const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const compatibilityHref=id=>'/catalog.html?kind=purchase&camera='+encodeURIComponent(id);

export function compatibleAccessories(product,data){
 const models=product.camera_model_ids||product.compatible_camera_model_ids||[];
 if(!models.length)return [];
 const families=new Set();
 return data.products.filter(p=>{
  if(p.kind!=='purchase'||(p.listing_id||p.id)===(product.listing_id||product.id)||!p.compatible_camera_model_ids?.some(id=>models.includes(id)))return false;
  const key=p.listing_id||p.id;if(families.has(key))return false;families.add(key);return true;
 }).sort((a,b)=>Number(a.status==='soldout')-Number(b.status==='soldout')||a.brand_id.localeCompare(b.brand_id));
}

export function compatibilitySection(product,data,card){
 const ids=product.camera_model_ids||product.compatible_camera_model_ids||[];
 const models=(data.camera_models||[]).filter(m=>ids.includes(m.id));
 if(!models.length)return '';
 const accessories=compatibleAccessories(product,data),groups=new Map();
 for(const p of accessories){if(!groups.has(p.brand_id))groups.set(p.brand_id,[]);groups.get(p.brand_id).push(p)}
 // Give different accessory manufacturers a place before filling the next row.
 const sample=[];let round=0;
 while(sample.length<12){let added=false;for(const items of groups.values())if(items[round]){sample.push(items[round]);added=true;if(sample.length===12)break}if(!added)break;round++}
 const bodies=product.compatible_camera_model_ids?(data.products||[]).filter(p=>p.kind==='purchase'&&p.camera_model_ids?.some(id=>ids.includes(id))):[];
 return `<section class="description compatible-accessories" aria-label="카메라별 케이지와 액세서리"><h2>${product.camera_model_ids?'이 카메라용 케이지·액세서리':'같은 카메라용 액세서리'}</h2><p>상품에 명시된 카메라 모델로 모았습니다. 카메라 세대와 선택 옵션, 함께 장착할 부속품을 확인해주세요.</p><nav class="category-chips" aria-label="호환 카메라 선택">${models.map(m=>`<a href="${compatibilityHref(m.id)}">${esc(m.name)}용 전체 보기 <small>${m.accessory_product_ids.length}</small></a>`).join('')}</nav>${bodies.length?`<p>함께 사용하는 카메라: ${bodies.slice(0,4).map(p=>`<a href="/item.html?id=${encodeURIComponent(p.id)}">${esc(p.name)}</a>`).join(' · ')}</p>`:''}${sample.length?`<div class="product-grid">${sample.map(card).join('')}</div>`:'<p>현재 등록된 전용 액세서리를 확인 중입니다. 필요한 구성은 나다운에 상담해주세요.</p>'}</section>`;
}

export function cameraSelection(data,current){
 const models=(data.camera_models||[]).filter(m=>m.accessory_product_ids.length).sort((a,b)=>a.name.localeCompare(b.name));
 if(!models.length)return '';
 return `<label for="compatible-camera-select">사용할 카메라</label><select id="compatible-camera-select"><option value="">모델 선택 · 전체 상품</option>${models.map(m=>`<option value="${esc(m.id)}" ${m.id===current?'selected':''}>${esc(m.name)} (${m.accessory_product_ids.length})</option>`).join('')}</select>`;
}
