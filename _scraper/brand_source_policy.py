"""Owner-selected purchase sources and private source matching audit."""
from collections import Counter, defaultdict
import json
from pathlib import Path
from sync_shop_sources import ROOT, OUT, save_json, stamp

POLICY=ROOT/'data/catalog/brand-source-policy.json'
AUDIT=ROOT.parent/'_private/nadaun-shop/catalog'
NAMES={'kpp':'KPP','smartstore':'우리 스마트스토어','imweb-dji':'기존 아임웹 DJI','l-mount':'엘디엘마운트','plthink':'유쾌한생각','avx':'AVX','clmedia':'씨엘미디어','cinemall':'시네몰'}


def selections():
    return json.loads(POLICY.read_text())['brands']


def inventory(candidate=None):
    from build_catalog import brand_id
    result=defaultdict(Counter)
    for source in NAMES:
        path=OUT/(source+'.json')
        snapshot=candidate if source=='avx' and candidate else json.loads(path.read_text()) if path.exists() else None
        if not snapshot:continue
        for p in snapshot['products'].values():
            if p.get('kind')=='purchase':result[brand_id(p['brand'])][source]+=1
    return result


def pending(candidate):
    chosen=selections();counts=inventory(candidate)
    return [{'brand_id':bid,'sources':dict(sources)} for bid,sources in sorted(counts.items())
        if sources.get('avx') and len(sources)>1 and chosen.get(bid,{}).get('source') not in sources]


def write_audit(catalog,candidate=None):
    chosen=selections();counts=inventory(candidate)
    rows=[]
    for p in catalog['products']:
        primary=next((o for o in p['offers'] if o['id']==p['id']),None)
        if not primary:raise ValueError('Primary product source is not traceable: '+p['id'])
        rows.append({'product_id':p['id'],'name':p['name'],'brand_id':p['brand_id'],'kind':p['kind'],
            'primary_source':primary['source'],'primary_source_product_id':primary['id'],
            'primary_url':primary['url'],'matched_sources':p['offers'],
            'brand_selected_source':chosen.get(p['brand_id'],{}).get('source') if p['kind']=='purchase' else None})
    report={'checked_at':stamp(),'catalogue_revision':catalog['meta']['revision'],
        'brands':[{'brand_id':bid,'source_product_counts':dict(c),'selection':chosen.get(bid),
            'selection_pending':len(c)>1 and bid not in chosen} for bid,c in sorted(counts.items())],
        'products':rows}
    AUDIT.mkdir(parents=True,exist_ok=True,mode=0o700)
    save_json(AUDIT/'source-matches.json',report)
    lines=['# 브랜드별 미러링 기준 사이트','',f"확인 시각: {report['checked_at']}",'',
        '상품별 원본 ID·URL·합쳐진 원본 목록은 같은 폴더의 source-matches.json에 저장합니다. 숫자는 원본 등록 건수입니다.','',
        '| 브랜드 | 사이트별 원본 등록 건수 | 대표 선택 |','|---|---|---|']
    for b in report['brands']:
        if len(b['source_product_counts'])<2:continue
        selection=b['selection'] or {}
        label=' + '.join(NAMES.get(s,s) for s in selection.get('sources',[selection.get('source')]) if s) or '선택 대기'
        lines.append('| '+b['brand_id']+' | '+' / '.join(f'{NAMES[s]} {n:,}' for s,n in b['source_product_counts'].items())+' | '+label+' |')
    (AUDIT/'brand-source-review.md').write_text('\n'.join(lines)+'\n')
    for p in (AUDIT/'source-matches.json',AUDIT/'brand-source-review.md'):p.chmod(0o600)
    return report
