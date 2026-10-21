'use strict';
const {ShopError,protect}=require('./security.cjs');
const supplierFields=['company','business_number','representative','contact_name','phone','mobile','fax','email'];
const termFields=['supplier_product_name','supplier_product_code','shipping','printing','notes','commission_percent','external_display'];
const clean=(v,max=1000)=>{if(v===undefined)return '';if(typeof v!=='string'||v.length>max||/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(v))throw new ShopError(400,'업체 정보 형식을 확인해주세요.');return v.trim();};
const id=value=>{if(typeof value!=='string'||! /^[1-9]\d{0,11}$/.test(value))throw new ShopError(400,'상품번호를 확인해주세요.');return value;};
function validate(input,clock){
 if(!input||typeof input!=='object'||Array.isArray(input)||!input.supplier||!input.terms||!input.evidence)throw new ShopError(400,'공급업체와 확인 근거를 입력해주세요.');
 const supplier=Object.fromEntries(supplierFields.map(k=>[k,clean(input.supplier[k],500)]));
 if(!supplier.company||Object.values(supplier).some(v=>/[\r\n]/.test(v))||supplier.email&&!/^[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+$/.test(supplier.email))throw new ShopError(400,'업체명과 연락처를 확인해주세요.');
 const terms=Object.fromEntries(termFields.map(k=>[k,clean(input.terms[k],10000)]));
 if(!['allowed','blocked','unknown'].includes(terms.external_display))throw new ShopError(400,'원본의 외부 노출 조건을 선택해주세요.');
 const evidence={kind:clean(input.evidence.kind,50),reference:clean(input.evidence.reference,1000),observed_at:clean(input.evidence.observed_at,60)};
 const observed=Date.parse(evidence.observed_at);
 if(!['owner_screenshot','authenticated_supplier_page','owner_export','operator_verified'].includes(evidence.kind)||!evidence.reference||!/(Z|[+-]\d\d:\d\d)$/.test(evidence.observed_at)||!Number.isFinite(observed)||observed>clock()+60000)throw new ShopError(400,'업체 확인 근거와 확인 시각을 입력해주세요.');
 return {supplier,terms,evidence};
}
function giftAdminService({db,catalog,product,dataKey,clock=()=>Date.now()}){
 const cipher=protect(dataKey);
 async function current(pid){return (await db.query('SELECT * FROM shop_gift_suppliers WHERE product_id=? ORDER BY version DESC LIMIT 1',[pid]))[0]||null;}
 async function latest(){return db.query('SELECT a.product_id,a.version,a.updated_at FROM shop_gift_suppliers a WHERE a.version=(SELECT MAX(b.version) FROM shop_gift_suppliers b WHERE b.product_id=a.product_id)');}
 return {
  async list(input={}){
   const data=catalog(),q=clean(input.q,120).normalize('NFKC').toLowerCase(),category=clean(input.category,80),status=clean(input.status,30),page=Number(input.page||1);
   if(!Number.isSafeInteger(page)||page<1||page>10000||!['','priced','unpriced','supplier','missing_supplier'].includes(status))throw new ShopError(400,'조회 조건을 확인해주세요.');
   const matches=new Map((await latest()).map(r=>[r.product_id,r]));
   const rows=data.products.filter(p=>(!q||[p.id,p.name,p.manufacturer_label].join(' ').normalize('NFKC').toLowerCase().includes(q))&&(!category||p.category_ids.includes(category))&&(!status||status==='priced'&&p.pricing_available||status==='unpriced'&&!p.pricing_available||status==='supplier'&&matches.has(p.id)||status==='missing_supplier'&&!matches.has(p.id)));
   return {meta:{...data.meta,supplier_matched_products:matches.size},categories:data.categories,total:rows.length,page,pages:Math.max(1,Math.ceil(rows.length/40)),products:rows.slice((page-1)*40,page*40).map(p=>({...p,supplier_registered:matches.has(p.id)}))};
  },
  async get(value){
   const pid=id(value),p=product(pid);if(!p)throw new ShopError(404,'상품을 찾을 수 없습니다.');
   const row=await current(pid);
   return {product:p,supplier_record:row?{...cipher.decrypt(row.private_cipher),version:row.version,updated_at:row.updated_at}:null,
    source_url:'https://nadaun-gift.com/new/shop/detail.php?code='+pid};
  },
  async save(value,input,actor){
   const pid=id(value),p=product(pid);if(!p)throw new ShopError(404,'상품을 찾을 수 없습니다.');
   if(!Number.isSafeInteger(input.version)||input.version<0)throw new ShopError(400,'업체 기록 버전을 확인해주세요.');
   const record={product_id:pid,product_name:p.name,...validate(input,clock)},now=clock();
   const prior=await current(pid);
   if(prior&&Date.parse(record.evidence.observed_at)<Date.parse(cipher.decrypt(prior.private_cipher).evidence.observed_at))throw new ShopError(409,'현재 등록된 근거보다 이전 시각입니다. 최신 원본의 실제 확인 시각을 입력해주세요.');
   const rows=await db.query('INSERT INTO shop_gift_suppliers(product_id,version,private_cipher,updated_at,actor_cipher) SELECT ?,?,?,?,? WHERE COALESCE((SELECT MAX(version) FROM shop_gift_suppliers WHERE product_id=?),0)=? RETURNING version',[pid,input.version+1,cipher.encrypt(record),now,cipher.encrypt({actor}),pid,input.version]);
   if(!rows.length)throw new ShopError(409,'다른 곳에서 업체 정보가 변경되었습니다. 새로고침 후 다시 확인해주세요.');
   return this.get(pid);
  }
 };
}
module.exports={giftAdminService,validate};
