"""HiPixel's original public navigation and product identity evidence."""
from copy import deepcopy
import re
import json
from pathlib import Path

BRAND_ROOTS={'24':'Blackmagic Design','25':'TVLOGIC','26':'COMPIX','28':'TERIS'}
EXCLUDED_CATEGORIES={'90':'개인결제: 특정 고객의 결제용 페이지, 일반 판매 상품이 아님'}
COLLECTION_CATEGORIES={'123':'베스트','124':'신제품'}


def navigation_role(source_id):
    if source_id in COLLECTION_CATEGORIES:return 'collection'
    if source_id in BRAND_ROOTS or source_id=='57':return 'wrapper'
    return 'category'


def category_payload(payload):
    if not isinstance(payload,list):
        raise ValueError('HiPixel category tree must be a list')
    rows=deepcopy(payload)
    excluded=set(EXCLUDED_CATEGORIES)
    for _ in rows:
        added={str(r['cate_no']) for r in rows if str(r['parent_cate_no']) in excluded}
        if added<=excluded:break
        excluded.update(added)
    return [r for r in rows if str(r['cate_no']) not in excluded]


def category_brand(category_ids,nodes):
    found=set()
    for cid in category_ids:
        cursor=str(cid);seen=set()
        while cursor in nodes:
            if cursor in seen:raise ValueError('HiPixel category cycle')
            seen.add(cursor)
            if cursor in BRAND_ROOTS:
                found.add(BRAND_ROOTS[cursor]);break
            cursor=nodes[cursor].get('parent_id')
    if len(found)>1:
        raise ValueError('HiPixel product belongs to conflicting named brands')
    return next(iter(found)) if found else ''


# Actual supplier menu IDs, kept separate from brand navigation. Accessory
# exceptions below were reviewed against the source's product names/categories.
TYPE_BY_CATEGORY={
    '29':'switcher','61':'video-control','62':'converter','30':'converter',
    '31':'camera','67':'cinema-camera','68':'studio-camera','105':'camera-expansion',
    '46':'video-recorder','47':'video-capture','48':'video-streaming',
    '49':'software','71':'editing-software','72':'editing-control','117':'audio-control',
    '50':'monitor','91':'monitor-recorder','51':'video-multiview','52':'video-routing',
    '99':'video-control','53':'network-storage','54':'converter','55':'video-compositing',
    '56':'film-scanner','111':'power-parts','25':'monitor','89':'power-parts',
    '84':'kpp:0710','85':'audio','86':'kpp:08','88':'camera-battery',
    '26':'video-graphics','80':'kpp:0110','81':'kpp:0130',
}
REVIEWED_TYPES=json.loads(Path(__file__).with_name('hipixel-reviewed-types.json').read_text())
TYPE_BY_PRODUCT={sid:rule['type'] for sid,rule in REVIEWED_TYPES.items()}
UNBRANDED_REVIEW_IDS={'294','359','360','361'}


def add_reviewed_navigation(product,categories):
    """Add explicit shop leaves only where the source has a wrapper alone.

    Original memberships and source IDs stay intact. These purpose nodes are
    labelled as our reviewed classification, never as a supplier menu ID.
    """
    if product.get('source')!='hipixel':return []
    bid=product['brand_id'];sid=str(product['source_id'])
    if bid=='unbranded' and sid in {'359','360'}:
        if product['name']!=REVIEWED_TYPES[sid]['expected_name']:
            raise ValueError('Reviewed rack identity changed: '+product['id'])
        parent='hipixel:b:unbranded:57';purpose='video-rack';label='랙·설치 부품'
    elif bid=='compix' and sid in {'291','292'}:
        expected={'291':'천하통일HD200 문자발생기(오버레이방식)','292':'천하통일HD200K 문자발생기(Key, Fill방식)'}
        if product['name']!=expected[sid]:
            raise ValueError('Reviewed graphics identity changed: '+product['id'])
        parent='hipixel:b:compix:26';purpose='video-graphics';label='문자발생기'
    else:return []
    if parent not in product['category_ids'] or parent not in categories:
        raise ValueError('Reviewed purpose source path changed: '+product['id'])
    cid=f'hipixel:b:{bid}:purpose:{purpose}'
    categories[cid]={'id':cid,'name':label,'parent_id':parent,'brand_id':bid,
        'position':999,'navigation_role':'reviewed-category'}
    product['category_ids'].append(cid)
    return [cid]


def apply_review(record,schema):
    sid=str(record['source_id'])
    if sid=='249' and 'description_missing' in record['content_issues']:
        if record['name']!='TERIS TS50CF' or record['brand']!='TERIS' or set(record['brand_category_ids'])!={'57','80','28'}:
            raise ValueError('Reviewed TS50CF description identity changed')
        record['description_text']='TERIS TS50CF는 TS50 유체 헤드와 카본 삼각대로 구성된 시스템입니다. 제조사 카탈로그 기준 최대 지지하중은 5kg이며 75mm 볼을 사용합니다. 헤드는 고정 드래그와 고정 카운터밸런스를 제공합니다.'
        record['description_notice']='제조사 카탈로그(2021) 기준 요약입니다. 현재 구성품과 상세 사양은 구매 상담에서 확인해 주세요.'
        record['description_evidence']={'source':'manufacturer_brochure_summary','year':2021,
            'url':'https://www.dedoweigertfilm.de/dwf-wAssets/img/Products/Teris/Teris_product_brochure_2021_V3.pdf',
            'verified_via':'indexed manufacturer brochure excerpt; direct PDF download unavailable',
            'reason':'HiPixel source description area is empty; no supplier specs invented'}
        record['content_issues'].remove('description_missing')
        record['detail_status']='verified' if not record['content_issues'] else 'review_required'
    if sid not in UNBRANDED_REVIEW_IDS:return
    expected=REVIEWED_TYPES[sid]
    declared=schema.get('brand',{})
    declared=declared.get('name','') if isinstance(declared,dict) else declared
    if (record['name']!=expected['expected_name'] or declared!='Blackmagicdesign_하이픽셀플러스'
            or set(record['brand_category_ids'])!=({'57','86'} if sid in {'294','361'} else {'57'})):
        raise ValueError('Reviewed unbranded accessory evidence changed: '+record['id'])
    # The source lists these under Other Equipment, with no manufacturer row.
    # Compatible Blackmagic devices in photographs are not the rack/cable maker.
    record['brand']='브랜드 미표기'
    record['brand_evidence']={'kind':'reviewed_manufacturer_not_stated','source_schema_label':declared,
        'evidence':expected['evidence'],'review':'hipixel-primary-20261018/brand-review-images'}
    record['content_issues']=[i for i in record['content_issues'] if i!='brand_membership_requires_review']
    if sid=='361':
        if not all(value in record['description_text'] for value in ('15cm','30cm')):
            raise ValueError('Reviewed cable length notice changed')
        record['options_require_confirmation']=True
        record['description_notice']='케이블 길이(15cm 또는 30cm)는 주문 전 확인이 필요합니다.'
    record['detail_status']='verified' if not record['content_issues'] else 'review_required'


def product_types(product,categories):
    source_ids={o['id'].removeprefix('hipixel-') for o in product.get('offers',[]) if o.get('source')=='hipixel'}
    if product['id'].startswith('hipixel-'):source_ids.add(product['id'].removeprefix('hipixel-'))
    if not source_ids:return []
    own_id=product['id'].removeprefix('hipixel-') if product['id'].startswith('hipixel-') else None
    if own_id in REVIEWED_TYPES and ' '.join(product['name'].split())!=' '.join(REVIEWED_TYPES[own_id]['expected_name'].split()):
        raise ValueError('HiPixel reviewed product title changed: '+product['id'])
    specific={TYPE_BY_PRODUCT[sid] for sid in source_ids if sid in TYPE_BY_PRODUCT}
    if len(specific)>1:raise ValueError('Conflicting HiPixel reviewed product purposes: '+product['id'])
    if specific:return sorted(specific)
    membership=[categories[cid] for cid in product.get('category_ids',[]) if cid.startswith('hipixel:') and cid in categories]
    def depth(c):
        result=0;seen=set()
        while c.get('parent_id'):
            if c['id'] in seen:raise ValueError('HiPixel product-type ancestry cycle')
            seen.add(c['id']);result+=1;c=categories[c['parent_id']]
        return result
    found=sorted((c for c in membership if c['id'].split(':')[-1] in TYPE_BY_CATEGORY),key=lambda c:(-depth(c),c.get('position',999)))
    if not found:return []
    name=product['name']
    # Compatible device names must not move installation/control parts into
    # the device itself, even when the supplier includes them in that family.
    for target,pattern in [('video-rack',r'rack\s*(?:kit|shelf)|랙.*(?:키트|브라켓)'),
        ('video-control',r'HyperDeck\s+Extreme\s+Control|Smart\s+Remote|Smart\s+Panel'),
        ('power-parts',r'Power\s+Supply|전원.*어댑터'),
        ('storage-dock',r'Media\s+Dock|MultiDock')]:
        if re.search(pattern,name,re.I):return [target]
    return [TYPE_BY_CATEGORY[found[0]['id'].split(':')[-1]]]


def blackmagic_type(name):
    """Verified manufacturer families for supplemental and older SKUs.

    Source categories win for HiPixel products. Avoid generic matches such
    as DeckLink ending in 'ink' and UltraStudio containing 'studio'.
    """
    rules=[
        ('cinema-camera',r'URSA\s+Cine\s+12K\s+LF\s*\+\s*EVF'),
        ('monitor',r'PYXIS\s+Monitor'),
        ('speakers',r'Audio\s+Monitor'),
        ('audio-cable',r'XLR.*Cable'),
        ('camera-expansion',r'PCIe\s+Cable\s+Kit'),
        ('screen-protection',r'보호\s*필름|액정\s*보호|screen\s*protector'),
        ('power-parts',r'Power\s+Supply|전원.*어댑터|Battery\s+(?:Plate|(?:Pro\s+)?Grip)|DC\s+Cable'),
        ('electronic-viewfinder',r'Viewfinder|뷰파인더|\bEVF\b'),
        ('kpp:0330',r'(?:PL|LPL|EF|B4|F)\s+Mount|Mount\s+(?:PL|LPL|EF|B4|F)\b|Shim\s+Kit'),
        ('kpp:0650',r'\bHandle\b|Pro\s+Grip'),
        ('video-rack',r'Rack\s+(?:Kit|Shelf)|랙.*(?:키트|브라켓)'),
        ('kpp:0140',r'Rosette\s+Plate'),('kpp:0740',r'Mic\s+Mount'),
        ('remote',r'(?:Zoom|Focus)\s+Demand'),('camera-rig',r'Broadcast\s+ENG\s+Kit'),
        ('camera-expansion',r'Camera\s+ProDock'),('storage-dock',r'Media\s+Dock|MultiDock'),
        ('ssd',r'Media\s+Module'),('video-control',r'Arduino\s+Shield|GPI\s+and\s+Tally'),
        ('audio-control',r'Fairlight.*Panel'),
        ('editing-control',r'DaVinci.*(?:Panel|Editor|Keyboard)|다빈치.*(?:패널|키보드|에디터)'),
        ('editing-software',r'DaVinci\s+Resolve\s+Studio|다빈치\s*리졸브\s*스튜디오|Fusion\s+Studio'),
        ('video-control',r'HyperDeck.*Control|Ultimatte.*Remote|ATEM.*Panel|Videohub.*Control|Smart\s+Panel'),
        ('video-capture',r'DeckLink|UltraStudio|Intensity|Media\s+Player'),
        ('converter',r'Converter|컨버터|Teranex|2110\s+IP|UpDownCross|StudioBridge|SDI\s+Expander|Optical\s+Module|Quad\s+SDI\s+to'),
        ('video-streaming',r'Web\s*Presenter|Streaming|Live\s+Encoder'),
        ('video-network',r'Ethernet\s+Switch'),('network-storage',r'Cloud\s+(?:Store|Dock|Pod|Backup)'),
        ('video-routing',r'Videohub|비디오허브'),('video-multiview',r'MultiView|멀티뷰'),
        ('monitor',r'SmartView|SmartScope'),('monitor-recorder',r'Video\s+Assist|비디오\s*어시스트'),
        ('video-recorder',r'HyperDeck|URSA\s+Mini\s+Recorder'),
        ('video-compositing',r'Ultimatte'),('film-scanner',r'Cintel'),
        ('studio-camera',r'(?:Micro\s+)?Studio\s+Camera'),
        ('cinema-camera',r'URSA|PYXIS|Pocket\s+Cinema|Cinema\s+Camera'),
        ('switcher',r'\bATEM\b|아템'),
    ]
    for target,pattern in rules:
        if re.search(pattern,name,re.I):return target
    return None
