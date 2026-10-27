"""Verified owner-requested supplier snapshots and explicit retail price rules.

Collectors retain source prices; this module applies retail policy to a copy only.
Motion9's legacy independent add-ons stay consultation-only, never a Cartesian
purchase variant. FUNOMAD has no public numeric prices, including option prices.
"""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import hashlib, json, re
from urllib.parse import urlsplit

SOURCES=('motion9','funomad','digitalcp','sunphoto')
DOMAINS={'motion9':'motionnine.cafe24.com','funomad':'funomad.com','digitalcp':'www.digitalcp.co.kr','sunphoto':'sunphoto.kr'}

def ids_digest(ids):
    return hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest()

def validate_snapshot(s):
    source=s.get('source'); ps=s.get('products',{})
    if source not in SOURCES or s.get('schema_version')!=1 or not s.get('complete'):
        raise ValueError('Unverified reviewed supplier snapshot')
    if not ps or s.get('product_count')!=len(ps) or s.get('coverage')!={'count':len(ps),'ids_sha256':ids_digest(ps)}:
        raise ValueError('Reviewed supplier product coverage differs')
    categories={c['id']:c for c in s.get('categories',[])}
    if len(categories)!=len(s.get('categories',[])):raise ValueError('Duplicate supplier category')
    for c in categories.values():
        if c.get('parent_id') and c['parent_id'] not in categories:raise ValueError('Missing supplier parent')
    for pid,p in ps.items():
        if p['id']!=pid or p['source']!=source or not pid.startswith(source+'-') or p.get('kind')!='purchase' or p.get('detail_status')!='verified':
            raise ValueError('Invalid reviewed supplier product identity: '+pid)
        if urlsplit(p['source_url']).hostname!=DOMAINS[source] or not p.get('evidence_sha256'):
            raise ValueError('Missing source evidence: '+pid)
        if not p.get('brand_category_ids') or any(c not in categories for c in p['brand_category_ids']):raise ValueError('Missing product category: '+pid)
        if not p.get('images',{}).get('main'):raise ValueError('Missing original product gallery: '+pid)
        if source=='funomad':
            if p.get('price') is not None or p.get('sale_price') is not None or p.get('status')!='inquiry':raise ValueError('FUNOMAD must be inquiry only')
            if any(o.get('price') is not None or o.get('additional_price') not in (None,0) for o in p.get('options',[])):raise ValueError('FUNOMAD option prices are not public')
        elif source=='motion9' and (not isinstance(p.get('price'),int) or p['price']<=0):raise ValueError('Motion9 base price requires verification')
        elif source in ('digitalcp','sunphoto'):
            if p.get('price') is not None and (isinstance(p['price'],bool) or not isinstance(p['price'],int) or p['price']<=0):raise ValueError('Invalid public supplier price')
            if source=='digitalcp':
                from sync_digitalcp_catalog import excluded
                if excluded(p['brand']):raise ValueError('Owner-excluded DigitalCP brand in candidate')
            if source=='sunphoto' and p['brand'].casefold() not in ('tamron','voigtlander'):raise ValueError('Sunphoto manufacturer is outside owner scope')
    return s

def markup_won(value):
    if value is None:return None
    if isinstance(value,bool) or not isinstance(value,int) or value<0:raise ValueError('Invalid source won amount')
    return int((Decimal(value)*Decimal('1.05')).quantize(Decimal(1),rounding=ROUND_HALF_UP))

def retail_product(raw):
    p=deepcopy(raw)
    if p['source']=='digitalcp':
        p['source_regular_price']=raw.get('price')
        p['price']=raw.get('sale_price')
        return p
    if p['source']=='funomad':
        p.update(price=None,sale_price=None,status='inquiry',supplier_status='inquiry',options_require_confirmation=True)
        for o in p.get('options',[]):o.update(price=None,additional_price=0)
        return p
    if p['source']!='motion9':return p
    p['price']=markup_won(raw['price']);p['sale_price']=markup_won(raw.get('sale_price',raw['price']))
    for o in p.get('options',[]):
        source_price=o.get('price');o['price']=markup_won(source_price)
        if p.get('independent_option_groups'):
            # These values are individual group rows, not combinations.
            o['additional_price']=0
            prefix='추가 구성' if o.get('role')=='addon' else '기본 구성'
            amount='변경 없음' if o.get('unchanged') else f"{o['price']:,}원" if o['price'] is not None else '문의'
            o['name']=f"{prefix} · {o['group_name']} · {o['label']} · {amount}"
        else:o['additional_price']=o['price']-p['price'] if o['price'] is not None else 0
    return p

def reference_price_overrides(products,redirects,snapshots,overrides):
    for pid,rule in overrides.items():
        if rule.get('price_source')!='smartstore':continue
        p=products.get(redirects.get(pid,pid))
        if not p:continue
        rid=rule['reference_product_id'];r=snapshots.get('smartstore',{}).get('products',{}).get(rid)
        if not r or r.get('kind')!='purchase' or r.get('name')!=rule.get('reference_expected_name'):
            raise ValueError('Owner price reference identity changed: '+rid)
        amount=r.get('sale_price') if r.get('sale_price') is not None else r.get('price')
        if not isinstance(amount,int) or amount<=0:raise ValueError('Owner price reference unavailable: '+rid)
        p.update(price=amount,sale_price=amount)
        for key in ('price','sale_price'):p['_provenance']['fields'][key]={'source':'smartstore','product_id':rid,'url':r['source_url'],'rule':'owner_reference_price'}


def apply_retired_redirects(products,redirects,rules):
    for old,rule in rules.items():
        target=redirects.get(rule['target_id'],rule['target_id'])
        item=products.get(target)
        if old in products and not products[old].get('hidden'):
            raise ValueError('Retired product unexpectedly active: '+old)
        if (not item or item.get('hidden') or item['brand_id']!=rule['expected_brand_id']
            or item['kind']!=rule['expected_kind'] or not rule.get('evidence')
            or (rule.get('expected_target_name') and item['name']!=rule['expected_target_name'])):
            raise ValueError('Retired product replacement needs review: '+old)
        redirects[old]=target
