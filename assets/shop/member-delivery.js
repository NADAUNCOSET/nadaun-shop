// Read-only member/previous-order choices. Personal details stay out of browser storage.
const shippingKeys=['name','phone','postcode','address','address_detail'];
const fieldsFor=contactOnly=>contactOnly?shippingKeys.slice(0,2):shippingKeys;
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const limits={name:60,phone:20,postcode:5,address:160,address_detail:100};
function contact(value,contactOnly){return Object.fromEntries(fieldsFor(contactOnly).map(key=>{
 const text=typeof value?.[key]==='string'?value[key].trim():'';
 return [key,text.length<=limits[key]&&!/[\x00-\x1f\x7f<>]/.test(text)?text:''];
}));}
export function deliveryData(value,contactOnly=false){
 if(value?.authenticated!==true||!value.profile||!Array.isArray(value.recent))throw Error('회원 배송 정보를 확인하지 못했습니다.');
 return {profile:contact(value.profile,contactOnly),recent:value.recent.slice(0,10).map(row=>contact(row,contactOnly))};
}
export function chooserHTML(data,contactOnly=false){
 const title=contactOnly?'예약자 정보 선택':'배송지 선택';
 return '<strong>'+title+'</strong><div class="member-delivery-actions"><button type="button" class="button-outline" data-delivery-profile>회원정보로 입력</button><button type="button" class="button-outline" data-delivery-clear>직접 입력</button></div>'+
  (data.recent.length?'<label>'+ (contactOnly?'최근 예약자':'최근 배송지')+'<select data-delivery-recent><option value="">선택하면 입력됩니다</option>'+data.recent.map((r,i)=>'<option value="'+i+'">'+escape([r.name,r.phone,...(!contactOnly?[r.address,r.address_detail]:[])].filter(Boolean).join(' · '))+'</option>').join('')+'</select></label>':'<p>이전 주문의 '+(contactOnly?'예약자 정보':'배송지')+'가 있으면 여기서 선택할 수 있습니다.</p>')+
  '<p data-delivery-status role="status" aria-live="polite">가입 정보에 없는 항목은 직접 입력해주세요. 선택한 내용은 수정할 수 있습니다.</p>';
}
export function applyDelivery(form,value,{contactOnly=false,keepMissing=false}={}){
 const keys=fieldsFor(contactOnly),fields=keys.map(key=>form.elements.namedItem(key));
 if(fields.some(field=>!field||field.disabled))return {applied:false,missing:[]};
 const source=contact(value,contactOnly);
 for(let i=0;i<keys.length;i++)if(!keepMissing||source[keys[i]]){
  fields[i].value=source[keys[i]];
  fields[i].dispatchEvent(new Event('input',{bubbles:true}));fields[i].dispatchEvent(new Event('change',{bubbles:true}));
 }
 return {applied:true,missing:keys.filter(key=>!source[key])};
}
const mounted=new WeakMap();
export async function mountDeliveryChooser(form,{contactOnly=false,fetcher=globalThis.fetch}={}){
 if(!form||!form.isConnected)return null;
 if(mounted.has(form))return mounted.get(form);
 const first=form.elements.namedItem('name');if(!first)return null;
 const doc=form.ownerDocument,root=doc.createElement('section');root.className='member-delivery-picker';root.setAttribute('aria-label',contactOnly?'예약자 정보 선택':'배송지 선택');
 first.closest('label').before(root);mounted.set(form,root);
 if(!doc.querySelector('link[data-member-delivery-style]')){const css=doc.createElement('link');css.rel='stylesheet';css.href='/assets/shop/member-delivery.css?v=20261031';css.setAttribute('data-member-delivery-style','');doc.head.append(css);}
 async function load(){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  root.textContent='회원정보와 최근 '+(contactOnly?'예약자를':'배송지를')+' 확인하고 있습니다.';
  try{
   const response=await fetcher('/api/members?action=delivery'+(contactOnly?'&contact=1':''),{credentials:'same-origin',cache:'no-store',signal:controller.signal});
   if(response.status===401){root.innerHTML='<p><a href="/account.html">로그인하고 회원정보·최근 '+(contactOnly?'예약자':'배송지')+' 선택 →</a></p>';return;}
   if(!response.ok)throw Error();
   const data=deliveryData(await response.json(),contactOnly);if(!form.isConnected)return;
   root.innerHTML=chooserHTML(data,contactOnly);
   const status=root.querySelector('[data-delivery-status]'),recent=root.querySelector('[data-delivery-recent]');
   const choose=(value,keepMissing=false)=>{
    const result=applyDelivery(form,value,{contactOnly,keepMissing});
    status.textContent=!result.applied?'주문 처리 중에는 입력한 정보를 바꿀 수 없습니다.':result.missing.length&&keepMissing?'회원정보를 입력했습니다. 저장되지 않은 항목은 직접 입력해주세요.':'선택한 정보를 입력했습니다. 필요한 부분은 수정해주세요.';
   };
   root.querySelector('[data-delivery-profile]').onclick=()=>{choose(data.profile,true);if(recent)recent.value='';};
   if(recent)recent.onchange=()=>{const i=Number(recent.value);if(recent.value!==''&&Number.isInteger(i)&&data.recent[i])choose(data.recent[i]);};
   root.querySelector('[data-delivery-clear]').onclick=()=>{const result=applyDelivery(form,{}, {contactOnly});if(result.applied){if(recent)recent.value='';status.textContent='새 정보를 직접 입력해주세요.';first.focus();}};
  }catch{
   if(!form.isConnected)return;
   root.innerHTML='<p>회원정보를 불러오지 못했습니다. 직접 입력하거나 다시 확인해주세요.</p><button type="button" class="button-outline" data-delivery-retry>다시 확인</button>';
   root.querySelector('[data-delivery-retry]').onclick=()=>{void load();};
  }finally{clearTimeout(timer);}
 }
 await load();return root;
}
