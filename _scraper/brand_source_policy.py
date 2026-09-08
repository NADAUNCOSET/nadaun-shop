"""Owner-selected purchase sources and private source matching audit."""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from sync_shop_sources import ROOT, OUT, save_json, stamp
from private_storage import PRIVATE_DIRECTORY

POLICY=ROOT/'data/catalog/brand-source-policy.json'
AUDIT=PRIVATE_DIRECTORY/'catalog'
NAMES={'kpp':'KPP','smartstore':'우리 스마트스토어','imweb':'기존 아임웹','imweb-dji':'기존 아임웹 DJI','l-mount':'엘디엘마운트','plthink':'유쾌한생각','avx':'AVX','clmedia':'씨엘미디어','cinemall':'시네몰'}
NAMES['dji-official']='DJI 공식 한국 스토어'


def selections():
    return json.loads(POLICY.read_text())['brands']


def policy_fingerprint():
    return hashlib.sha256(POLICY.read_bytes()).hexdigest()


def purchase_source_allowed(product, choices=None):
    """An explicit exclusive purchase selection cannot replace rental stock."""
    if product.get('kind') != 'purchase':return True
    from build_catalog import brand_id
    choice=(choices if choices is not None else selections()).get(brand_id(product['brand']),{})
    return not choice.get('exclusive') or product.get('source')==choice['source']


def publishable_ids(snapshot):
    choices=selections()
    return {pid for pid,p in snapshot['products'].items() if purchase_source_allowed(p,choices)}


def snapshots(candidate=None):
    """Published snapshots plus the current verified candidate, never old generations."""
    result={}
    for source in NAMES:
        path=OUT/(source+'.json')
        if source=='avx':path=next((p for p in (OUT/'avx-approved.json',OUT/'avx.json',OUT/'avx-aputure.json') if p.exists()),path)
        if path.exists():result[source]=json.loads(path.read_text())
    if candidate:
        result[candidate.get('source','avx')]=candidate
    else:
        for source in ('avx','clmedia','cinemall'):
            folder=ROOT/'_scraper/.sync-state'/source
            generation=folder/'generation.json'
            if generation.exists():folder=folder/json.loads(generation.read_text())['directory']
            path=folder/'catalogue-candidate.json'
            if path.exists():
                value=json.loads(path.read_text())
                if value.get('complete'):result[source]=value
    return result


def inventory(candidate=None):
    from build_catalog import brand_id
    result=defaultdict(Counter)
    for source,snapshot in snapshots(candidate).items():
        for p in snapshot['products'].values():
            if p.get('kind')=='purchase':result[brand_id(p['brand'])][source]+=1
    return result


def pending(candidate):
    chosen=selections();counts=inventory(candidate)
    return [{'brand_id':bid,'sources':dict(sources)} for bid,sources in sorted(counts.items())
        if sources.get('avx') and len(sources)>1 and chosen.get(bid,{}).get('source') not in sources]


def source_provenance(p,detail,snapshot):
    """Private field origins, initialized before merging and never sent to customers."""
    origin={'source':p['source'],'snapshot_source':snapshot['source'],'product_id':p['id'],'source_id':p['source_id'],
        'url':p['source_url'],'listing_checked_at':snapshot.get('collected_at'),
        'detail_checked_at':detail.get('checked_at') or p.get('detail_checked_at') or p.get('verified_at'),
        'source_modified_at':p.get('source_modified_at')}
    fields={key:deepcopy(origin) for key in ('name','price','sale_price','status','supplier_status','description_text','options','option_groups','images.thumb','images.main','images.detail')}
    # A full-detail snapshot without per-item timing only proves its batch time.
    if snapshot['source'] in ('l-mount','imweb-dji','imweb-promotions'):
        for field in fields.values():field['detail_batch_collected_at']=snapshot.get('collected_at')
    categories={cid:[deepcopy(origin)] for field in ('category_ids','type_ids','promotion_ids') for cid in p.get(field,[])}
    return {'record':origin,'fields':fields,'source_categories':categories}


def merge_category_provenance(primary,other):
    if '_provenance' not in primary or '_provenance' not in other:return
    target=primary['_provenance']['source_categories']
    for cid,origins in other['_provenance']['source_categories'].items():
        target.setdefault(cid,[])
        for origin in origins:
            if origin not in target[cid]:target[cid].append(deepcopy(origin))


def write_audit(catalog,candidate=None,provenance=None):
    chosen=selections();counts=inventory(candidate)
    previous=AUDIT/'source-matches.json'
    old=json.loads(previous.read_text()) if previous.exists() else {}
    # Publication-waiting reports reuse this build's exact provenance, not a
    # new supplier candidate's later price as the current live price origin.
    if provenance is None:
        provenance={p['product_id']:p.get('provenance') for p in old.get('products',[])} if old.get('catalogue_revision')==catalog['meta']['revision'] else {}
    public_counts=defaultdict(lambda:defaultdict(Counter));public_brands={b['id']:b.get('name',b['id']) for b in catalog.get('brands',[])}
    rows=[]
    for p in catalog['products']:
        primary=next((o for o in p['offers'] if o['id']==p['id']),None)
        if not primary:raise ValueError('Primary product source is not traceable: '+p['id'])
        public_counts[p['brand_id']][p['kind']][primary['source']]+=1
        public_brands.setdefault(p['brand_id'],p['brand_id'])
        origin=provenance.get(p['id'])
        rows.append({'product_id':p['id'],'name':p['name'],'brand_id':p['brand_id'],'kind':p['kind'],
            'primary_source':primary['source'],'primary_source_product_id':primary['id'],
            'primary_url':primary['url'],'matched_sources':p['offers'],
            'brand_selected_source':chosen.get(p['brand_id'],{}).get('source') if p['kind']=='purchase' else None,
            'source_id':(origin or {}).get('record',{}).get('source_id'),
            'provenance':origin,'provenance_verified':bool(origin),
            'displayed_price':p.get('price'),'displayed_sale_price':p.get('sale_price'),
            'displayed_status':p.get('status'),'supplier_status':p.get('supplier_status'),
            'displayed_category_ids':p.get('category_ids',[]),'navigation_category_ids':p.get('navigation_category_ids',[])})
    report={'schema_version':2,'checked_at':stamp(),'catalogue_revision':catalog['meta']['revision'],
        'public_brand_count':len(public_brands),'product_count':len(rows),
        'field_provenance_verified_products':sum(r['provenance_verified'] for r in rows),
        'brands':[{'brand_id':bid,'name':public_brands.get(bid,bid),'public':bid in public_brands,
            'source_product_counts':dict(counts.get(bid,{})),
            'published_primary_counts':{k:dict(v) for k,v in public_counts.get(bid,{}).items()},
            'selection':chosen.get(bid),
            'selection_pending':len(counts.get(bid,{}))>1 and bid not in chosen} for bid in sorted(set(counts)|set(public_brands))],
        'products':rows,'public_products_sha256':product_digest(catalog),
        'publication':old.get('publication',{'state':'not_live_verified'}) if old.get('catalogue_revision')==catalog['meta']['revision'] and old.get('public_products_sha256')==product_digest(catalog) else {'state':'not_live_verified'}}
    AUDIT.mkdir(parents=True,exist_ok=True,mode=0o700)
    save_json(AUDIT/'source-matches.json',report)
    lines=['# 브랜드별 미러링 기준 사이트','',f"확인 시각: {report['checked_at']}",'',
        f"배포 대조: {report['publication']['state']} · revision {report['catalogue_revision']}",'',
        f"공개 브랜드 {len(public_brands):,}개 · 상품 레코드 {len(rows):,}개 · 필드 출처 검증 {report['field_provenance_verified_products']:,}개",'',
        '원본 등록 수에는 아직 공개하지 않은 검증 후보가 포함될 수 있습니다. 공개 출처는 현재 생성된 사이트 기준입니다. 원본 선택 대기는 기존 상품의 삭제나 변경을 뜻하지 않습니다.','',
        '상품별 원본 상품번호·주소·가격·상태·이미지·옵션·분류 출처와 확인 시각은 source-matches.json에 기록합니다. 렌탈은 구매 출처 선택과 별개로 유지합니다.','',
        '| 브랜드 | 공개 구매 기준 | 공개 렌탈 기준 | 원본 등록 수 | 대표 선택 |','|---|---|---|---|---|']
    for b in report['brands']:
        selection=b['selection'] or {}
        label=' + '.join(NAMES.get(s,s) for s in selection.get('sources',[selection.get('source')]) if s) or ('중복 선택 대기' if b['selection_pending'] else '단일 출처 유지')
        def describe(values):return ' / '.join(f'{NAMES.get(s,s)} {n:,}' for s,n in values.items()) or '—'
        lines.append('| '+b['name']+(' (수집 후보)' if not b['public'] else '')+' | '+describe(b['published_primary_counts'].get('purchase',{}))+' | '+describe(b['published_primary_counts'].get('rental',{}))+' | '+describe(b['source_product_counts'])+' | '+label+' |')
    (AUDIT/'brand-source-review.md').write_text('\n'.join(lines)+'\n')
    for p in (AUDIT/'source-matches.json',AUDIT/'brand-source-review.md'):p.chmod(0o600)
    return report


def product_digest(catalog):
    products=sorted(catalog['products'],key=lambda p:p['id'])
    return hashlib.sha256(json.dumps(products,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def verify_audit_live(catalog,release):
    """Verify every live price, stock state, category and offer before receipting."""
    path=AUDIT/'source-matches.json'
    report=json.loads(path.read_text())
    if (catalog['meta']['revision']!=report['catalogue_revision'] or
        release['revision']!=report['catalogue_revision'] or
        product_digest(catalog)!=report['public_products_sha256'] or
        len(catalog['products'])!=report['product_count']):
        raise ValueError('Live catalogue differs from the private source ledger')
    report['publication']={'state':'live_verified',**release,'verified_product_count':len(catalog['products'])}
    save_json(path,report);path.chmod(0o600)
    markdown=AUDIT/'brand-source-review.md'
    lines=markdown.read_text().splitlines()
    lines=[f"배포 대조: live_verified · {release['verified_at']} · revision {release['revision']} · 상품 {len(catalog['products']):,}개 전수 일치" if line.startswith('배포 대조:') else line for line in lines]
    markdown.write_text('\n'.join(lines)+'\n');markdown.chmod(0o600)
    return report['publication']
