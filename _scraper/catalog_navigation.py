"""Deterministic brand menus and a reviewable, NAS-only supplier register."""
from collections import Counter, defaultdict
import json
from pathlib import Path

SUPPLEMENTAL_REVIEW=json.loads(Path(__file__).with_name('hipixel-supplemental-navigation.json').read_text())


def reviewed_product_type(product):
    rule=SUPPLEMENTAL_REVIEW.get(product['id'])
    if not rule:return None
    if product['name']!=rule['expected_name'] or product['brand_id']!=rule['brand_id']:
        raise ValueError('Reviewed supplemental product identity changed: '+product['id'])
    return rule.get('product_type')


def unify_reviewed_navigation(products,categories,brands,audit):
    """Our menu mapping, never a claim of membership in a supplier inventory."""
    for bid in ('blackmagic','tvlogic','teris'):
        report=audit['brands'].get(bid,{})
        if report.get('preferred_source')!='hipixel':continue
        rows=[p for p in products if p['brand_id']==bid and p['kind']=='purchase']
        mapped=[]
        for p in rows:
            rule=SUPPLEMENTAL_REVIEW.get(p['id'])
            jib=bid=='teris' and 'type:jib' in p['type_ids']
            if any(c.startswith('hipixel:') for c in p['navigation_category_ids']) and not jib:continue
            if jib:
                target='hipixel:b:teris:purpose:jib'
                categories.setdefault(target,{'id':target,'name':'크레인·지미집','brand_id':bid,
                    'parent_id':'hipixel:b:teris:28','position':998,'navigation_role':'reviewed-category'})
            elif rule:
                reviewed_product_type(p)  # Exact-title and brand guard.
                target=rule['category_id']
            else:
                raise ValueError('New supplemental brand menu requires review: '+p['id'])
            path=[];cursor=target
            while cursor:
                if cursor in path or cursor not in categories or categories[cursor].get('brand_id')!=bid:
                    raise ValueError('Invalid reviewed navigation target: '+target)
                path.insert(0,cursor);cursor=categories[cursor].get('parent_id')
            mapped.append({'product_id':p['id'],'original_navigation':p['navigation_category_ids'],
                'reviewed_navigation':path,'basis':'reviewed_product_purpose','rule_file':'_scraper/hipixel-supplemental-navigation.json'})
            p['navigation_category_ids']=path
        brands[bid]['navigation_category_ids']=list(dict.fromkeys(cid for p in rows for cid in p['navigation_category_ids']))
        report['reviewed_navigation']=mapped
        report['fallback_products']=len({p.get('listing_id',p['id']) for p in rows if not any(c.startswith('hipixel:') for c in p['navigation_category_ids'])})


def arrange_categories(categories, brands, navigation_audit):
    """Preserve identities/ancestry; order parents beside their descendants."""
    original={cid:i for i,cid in enumerate(categories)}
    brand_rank={b['id']:i for i,b in enumerate(brands)}
    children=defaultdict(list)
    for c in categories.values():
        if c.get('parent_id') and c['parent_id'] not in categories:
            raise ValueError('Missing category parent: '+c['id'])
        children[c.get('parent_id')].append(c)
    def key(c):
        bid=c.get('brand_id')
        preferred=navigation_audit.get('brands',{}).get(bid,{}).get('preferred_source')
        return (brand_rank.get(bid,len(brands)),c.get('scope',''),
                0 if preferred and c['id'].startswith(preferred+':') else 1,
                c.get('position',original[c['id']]),original[c['id']])
    result={}
    def walk(parent,ancestors):
        for position,c in enumerate(sorted(children[parent],key=key)):
            cid=c['id']
            if cid in ancestors:raise ValueError('Category cycle: '+cid)
            result[cid]={**c,'navigation_position':position}
            walk(cid,ancestors|{cid})
    walk(None,set())
    if set(result)!=set(categories):raise ValueError('Category tree has unreachable nodes')
    return result


def write_register(catalog,navigation_audit,choices,directory):
    from brand_source_policy import NAMES
    from sync_shop_sources import save_json,stamp
    products=defaultdict(list)
    for p in catalog['products']:
        if p['kind']=='purchase':products[p['brand_id']].append(p)
    rows=[]
    for rank,b in enumerate(catalog['brands'],1):
        ps=products[b['id']];counts=Counter()
        sources=Counter(o['source'] for p in ps for o in p['offers'])
        for p in ps:
            primary=next(o for o in p['offers'] if o['id']==p['id'])
            counts[primary['source']]+=1
        choice=choices.get(b['id'],{})
        main=choice.get('source') or (sorted(counts,key=lambda s:(-counts[s],s))[0] if counts else None)
        nav=navigation_audit.get('brands',{}).get(b['id'],{})
        rows.append({'position':rank,'brand_id':b['id'],'name':b['name'],
            'primary_source':main,'category_source':nav.get('preferred_source'),
            'selection_basis':('owner_selected' if choice.get('confirmed_by')=='owner' else 'operator_source_review') if choice else 'current_primary_coverage' if main else 'rental_only',
            'supplemental_sources':[s for s in sorted(sources) if s!=main],
            'listing_count':len({p.get('listing_id',p['id']) for p in ps}),
            'variant_count':len(ps),'primary_counts':dict(counts),
            'category_fallback_count':nav.get('fallback_products',0),
            'unclassified_count':nav.get('unclassified_products',0)})
    report={'version':1,'checked_at':stamp(),'revision':catalog['meta']['revision'],
            'publication_state':'not_live_verified','brands':rows}
    save_json(directory/'brand-source-register.json',report)
    label=lambda s:NAMES.get(s,s) if s else '—'
    lines=['# 브랜드별 기준 사이트와 카테고리 순서','',
        f"생성 시각: {report['checked_at']} · revision {report['revision']} · 운영 배포 검증 전",'',
        '대표가 지정한 기준은 우선 적용합니다. 미지정 브랜드는 현재 실제 주 상품 수가 가장 많은 사이트를 관리 기준으로 표시합니다. 이 정리만으로 기존 상품 가격이나 주 출처를 일괄 변경하지 않습니다.',
        '주 사이트에 없는 상품은 보조 사이트로 보완합니다. 동일 모델·규격·색상·구성·옵션이 검증된 중복만 하나의 상품으로 통합하며, 렌탈과 구매는 별개입니다.',
        '메뉴는 브랜드 → 제품군 → 세부 종류 순서입니다. 신제품·베스트는 제품 종류가 아니며, 전체 제품 종류 보기는 브랜드 분류와 별도로 같은 상품을 연결합니다.','',
        '| 순서 | 브랜드 | 주 기준 사이트 | 보조 사이트 | 카테고리 기준 | 구매 목록 | 결정 근거 |',
        '|---:|---|---|---|---|---:|---|']
    for r in rows:
        basis={'owner_selected':'대표 지정','operator_source_review':'원본 확인','current_primary_coverage':'현행 주 상품 수','rental_only':'렌탈 전용'}[r['selection_basis']]
        lines.append(f"| {r['position']} | {r['name'].replace('|','/')} | {label(r['primary_source'])} | {', '.join(label(s) for s in r['supplemental_sources']) or '—'} | {label(r['category_source'])} | {r['listing_count']} | {basis} |")
    (directory/'brand-source-register.md').write_text('\n'.join(lines)+'\n')
