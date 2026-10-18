const test=require('node:test'),assert=require('node:assert/strict');
const {validateCatalog,idsDigest}=require('../../server/catalog-release-check.cjs');
function fixture(){return {
  meta:{product_count:1,listing_count:1},brands:[{id:'b',purchase_count:1,rental_count:0,navigation_category_ids:['h:root','h:child']}],
  categories:[{id:'h:root',brand_id:'b',parent_id:null,navigation_position:0},
    {id:'h:child',brand_id:'b',parent_id:'h:root',navigation_position:0},
    {id:'type:camera',brand_id:null,parent_id:null,scope:'product',navigation_position:1}],
  products:[{id:'h-1',kind:'purchase',brand_id:'b',category_ids:['h:root','h:child'],navigation_category_ids:['h:root','h:child'],type_ids:['type:camera'],offers:[{id:'h-1',source:'h'}]}],redirects:{'old-1':'h-1'}
}}
test('a complete classified release passes',()=>assert.deepEqual(validateCatalog(fixture(),{require_positions:true,source_inventories:{h:{count:1,sha256:idsDigest(['h-1'])}}}),[]));
for(const [name,mutate,expected] of [
  ['category cycle',c=>c.categories[0].parent_id='h:child','Category cycle'],
  ['wrong brand',c=>c.categories[1].brand_id='other','Cross-brand'],
  ['lost inventory',c=>c.products=[],'Product total mismatch'],
  ['wrong family',c=>c.products[0].listing_id='missing','Invalid product family'],
  ['broken redirect',c=>c.redirects['old-1']='missing','Broken duplicate redirect'],
  ['duplicated source identity',c=>c.products[0].offers.push({id:'h-1',source:'h'}),'Duplicate supplier product'],
  ['lost classification',c=>c.products[0].type_ids=[],'Missing product-type'],
  ['collection in product menu',c=>c.categories[1].navigation_role='collection','Collection mixed'],
  ['missing parent membership',c=>c.products[0].navigation_category_ids=['h:child'],'Incomplete menu ancestry'],
  ['wrong sibling position',c=>c.categories[1].navigation_position=9,'Unstable sibling order'],
])test(name+' blocks deployment',()=>{const c=fixture();mutate(c);assert(validateCatalog(c,{require_positions:true}).some(e=>e.includes(expected)))});
test('a changed supplier inventory cannot pass the approved source digest',()=>assert(validateCatalog(fixture(),{source_inventories:{h:{count:2,sha256:idsDigest(['h-1','h-2'])}}}).some(e=>e.includes('Incomplete source inventory'))));
test('a lower-priority duplicate cannot become canonical',()=>{const c=fixture();c.products[0].offers.push({id:'hipixel-1',source:'hipixel'});assert(validateCatalog(c,{primary_sources:{b:'hipixel'}}).some(e=>e.includes('Wrong preferred supplier')))});
