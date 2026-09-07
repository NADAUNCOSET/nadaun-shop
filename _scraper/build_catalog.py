"""Build NADAUN's independent brand/category catalogue from verified sources."""
import argparse
import ast
from collections import Counter,defaultdict
from copy import deepcopy
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import quote
from sync_shop_sources import ROOT,OUT,clean,save_json
from enrich_shop_sources import CACHE,shard,source_fingerprint

PUBLIC=ROOT/'data/catalog'

def slug(value):
    value=clean(value).casefold()
    ascii_slug=re.sub(r'[^a-z0-9]+','-',value).strip('-')
    return ascii_slug or 'brand-'+hashlib.sha256(value.encode()).hexdigest()[:10]

def brand_dictionary():
    aliases={}
    tree=ast.parse((ROOT/'_scraper/kpp.py').read_text())
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='BRANDS' for t in node.targets):
            for name,key in ast.literal_eval(node.value):
                if not key.startswith('_'): aliases[name.casefold()]=key
    extras={
      'dji':['디지아이','디제이아이'], 'lee-filters':['리필터','lee filters'],
      'aurora':['오로라','오로라라이트뱅크'], 'matthews':['매튜스','맷세스'],
      'benro':['벤로'], 'libec':['리벡'], 'savage':['사베지'], 'valens':['발렌스'],
      'broncolor':['브론컬러'], 'arturia':['아투리아'], 'blackmagic':['blackmagic design','블랙매직디자인'],
      'kumkwang':['금광정밀'], 'tenba':['텐바'], 'teris':['테리스'], 'swit':['스위트'],
      'wacom':['와콤'], 'lexar':['렉사'], 'fomex':['포멕스','포맥스'], 'visgo':['비스고'],
      'samyang':['삼양옵틱스'], 'qon':['큐온'], 'edelkrone':['에델크론'],
      'hoverair':['호버에어'], 'fxlion':['에프엑스라이온'], 'sedona':['세도나'],
      'motion9':['모션나인'], 'xtar':['엑스타'], 'genelec':['제네렉'],
      'eimage':['e-image','이미지그립'], 'sachtler':['셔틀러'], 'gitzo':['짓죠'],
      'phaseone':['페이즈원','phase one'], 'misonics':['미소닉스'], 'pentax':['펜탁스'],
      'sekonic':['세코닉'], 'saramonic':['사라모닉'], 'eizo':['에이조'],
      'rocknroller':['락앤롤러'], 'hahnel':['하넬'], 'sandisk':['샌디스크'],
      'lemark':['르마크'], 'ricoh':['리코'], 'peribounce':['페리바운스'],
      'epson':['앱손'], 'megadap':['메가뎁'], 'benq':['벤큐'], 'anyport':['애니포트'],
      'ulanzi':['울란지'], 'rainbowbene':['레인보우베네','나다운 스튜디오'],
      'captureone':['캡쳐원'], 'metabones':['메타본즈'], 'ecoflow':['에코플로우'],
      'datacolor':['데이터컬러'], 'tvlogic':['티브이로직'], 'tokina-cinema':['tokina cinema','cinema'],
      'hy':['h&y'], 'tethertools':['테더툴스'], 'pgytech':['피지테크'], 'smallrig':['스몰리그'],
    }
    for key,names in extras.items():
        for name in names+[key]: aliases[name.casefold()]=key
    return aliases

ALIASES=brand_dictionary()
DISPLAY={'hy':'H&Y','eimage':'E-IMAGE','blackmagic':'Blackmagic Design','rainbowbene':'NADAUN','lee-filters':'LEE Filters','tokina-cinema':'TOKINA CINEMA','visgo':'VSGO'}

def brand_id(raw): return ALIASES.get(clean(raw).casefold(),slug(raw or '기타 브랜드'))

def product_name(name):
    # Only remove the store's repeated prefix, preserving bundle/variant text.
    return re.sub(r'^\[\s*[^\]]*레인보우베네\s*\]\s*','',name).strip()

def model_key(p):
    if p['kind']!='purchase': return None
    if p['brand_id']=='tilta':
        tokens=set(re.findall(r'(?<![A-Z0-9])(?:TA|ES|WLC|MB|UBP|TGA|TT)-[A-Z0-9]+(?:-[A-Z0-9]+)+(?![A-Z0-9])',p['name'].upper()))
        return next(iter(tokens)) if len(tokens)==1 else None
    if p['brand_id']!='smallrig':return None
    tokens=set(re.findall(r'(?<![A-Z0-9])(?:SR)?(\d{3,4}[A-Z]?)(?![A-Z0-9])',p['name'].upper()))
    # Merge only unique, unambiguous SmallRig model numbers. Never fuzzy names.
    return next(iter(tokens)) if len(tokens)==1 else None

def build(allow_pending=False):
    source_files=['kpp','smartstore','imweb-dji']
    snapshots={key:json.loads((OUT/(key+'.json')).read_text()) for key in source_files}
    if not all(s.get('complete') for s in snapshots.values()): raise RuntimeError('Incomplete source snapshot')
    products={}; categories={}; brands={}; details={}; coverage=Counter()
    def add_brand(raw):
        bid=brand_id(raw)
        if bid not in brands: brands[bid]={'id':bid,'name':DISPLAY.get(bid,bid.upper() if not bid.startswith('brand-') else raw),'aliases':[],'logo':''}
        if raw not in brands[bid]['aliases']:brands[bid]['aliases'].append(raw)
        return bid
    for b in snapshots['kpp']['brands']:
        bid=add_brand(b['name']); brands[bid]['logo']=b['logo'];brands[bid]['featured']=True
    add_brand('DJI');brands['dji']['featured']=True
    for source,s in snapshots.items():
        for cat in s.get('categories',[]):
            c=deepcopy(cat)
            if source=='kpp':
                scope=c['scope'];bid=brand_id(scope.split(':',1)[1]) if scope.startswith('brand:') else None
                prefix='kpp:'+('b:'+bid if bid else 'p')+':'
            else:bid='dji';prefix='imweb:b:dji:'
            c.update(id=prefix+c['id'],parent_id=prefix+c['parent_id'] if c['parent_id'] else None,brand_id=bid)
            categories[c['id']]={k:c[k] for k in ('id','name','parent_id','brand_id')}
        cached={}
        if source!='imweb-dji':
            for f in (CACHE/source).glob('*.json'):
                if re.fullmatch('[a-f0-9]{2}',f.stem):cached.update(json.loads(f.read_text()))
        for pid,p0 in s['products'].items():
            p=deepcopy(p0);p['brand_id']=add_brand(p['brand']);p['name']=product_name(p['name'])
            bid=p['brand_id'];membership=[];types=[]
            if source=='kpp':
                for mall in p.get('brand_mall_ids',[]):
                    mbid=brand_id(mall)
                    for cid in p.get('brand_category_ids',[]):
                        key=f'kpp:b:{mbid}:{cid}'
                        if key in categories:membership.append(key)
                types=['kpp:p:'+cid for cid in p.get('product_category_ids',[]) if 'kpp:p:'+cid in categories]
                if not membership:
                    for tid in types:
                        source_cat=categories[tid]
                        key=f'kpp:b:{bid}:global:'+tid.split(':')[-1]
                        parent=source_cat['parent_id']
                        categories.setdefault(key,{'id':key,'name':source_cat['name'],'parent_id':f'kpp:b:{bid}:global:'+parent.split(':')[-1] if parent else None,'brand_id':bid})
                        membership.append(key)
                p['status']='inquiry'
            elif source=='imweb-dji': membership=['imweb:b:dji:'+cid for cid in p.get('brand_category_ids',[])]
            else:
                path=p.get('source_category_path') or [];ids=p.get('source_category_ids') or []
                # Naver standard classifications are retained separately from
                # supplier brand categories; no claim to be store display IDs.
                parent=None
                for cid,name in zip(ids[1:],path[1:]):
                    key=f'naver:b:{bid}:{cid}'
                    categories.setdefault(key,{'id':key,'name':name,'parent_id':parent,'brand_id':bid})
                    membership.append(key);parent=key
                # Flat category names cross brands for the later product view.
                if ids and path:
                    key='naver:p:'+ids[-1]
                    categories.setdefault(key,{'id':key,'name':path[-1],'parent_id':None,'brand_id':None})
                    types.append(key)
            p['category_ids']=list(dict.fromkeys(membership));p['type_ids']=types
            d=cached.get(pid,{})
            if source=='smartstore' and d.get('source_modified_at')!=p.get('source_modified_at'):
                d={}
            if source=='kpp' and d.get('source_fingerprint')!=source_fingerprint(p0):
                d={}
            if source=='imweb-dji':d={'detail_status':'verified','description_text':p.get('description_text',''),'images':p['images']}
            if d.get('detail_status')=='verified':coverage[source]+=1
            elif not allow_pending:raise RuntimeError('Unverified product detail: '+pid)
            if d.get('unavailable'):
                continue
            p['images'].update(d.get('images') or {})
            if source=='kpp':
                p['images']['detail']=[u for u in p['images'].get('detail',[]) if '/shop/images/' not in u]
            if source=='kpp' and d.get('detail_status')=='verified':p['price']=d['price'];p['sale_price']=d['sale_price']
            p['offers']=[{'source':p['source'],'url':p['source_url'],'status':p['status'],'price':p.get('sale_price'),'id':pid}]
            details[pid]={k:d.get(k) for k in ('description_text','options','option_groups','shipping') if d.get(k)}
            details[pid]['images']=p['images'];details[pid]['source_id']=p['source_id']
            products[pid]=p
    # Exact same model must be unique in each source. Ambiguity stays separate.
    candidates=defaultdict(lambda:defaultdict(list))
    for p in products.values():
        key=model_key(p)
        if key:candidates[(p['brand_id'],key,p['kind'])][p['source']].append(p['id'])
    redirects={};merge_count=0
    for sources in candidates.values():
        if len(sources.get('kpp',[]))!=1 or len(sources.get('smartstore',[]))!=1:continue
        sid,kid=sources['smartstore'][0],sources['kpp'][0]
        own,supplier=products[sid],products[kid]
        own['category_ids']=list(dict.fromkeys(own['category_ids']+supplier['category_ids']))
        own['type_ids']=list(dict.fromkeys(own['type_ids']+supplier['type_ids']))
        own['offers']+=supplier['offers'];own['supplier_status']=supplier.get('supplier_status')
        for kind in ('main','detail'):
            if not details[sid]['images'].get(kind):details[sid]['images'][kind]=details[kid]['images'].get(kind,[])
        redirects[kid]=sid;del products[kid];merge_count+=1
    config_path=PUBLIC/'overrides.json'
    config=json.loads(config_path.read_text()) if config_path.exists() else {'products':{},'brand_order':[],'category_order':[],'category_browsing_enabled':False}
    for pid,override in config.get('products',{}).items():
        p=products.get(redirects.get(pid,pid))
        if p:
            for key in ('name','price','sale_price','hidden','category_ids','type_ids','status'):
                if key in override:p[key]=deepcopy(override[key])
    asset_path=PUBLIC/'asset-manifest.json'
    assets=json.loads(asset_path.read_text()) if asset_path.exists() else {}
    public_products=[];public_details=defaultdict(dict)
    for pid,p in products.items():
        if p.get('hidden'):continue
        main=p['images'].get('main') or []
        thumb=p['images'].get('thumb') or (main[0] if main else '')
        if pid in assets and assets[pid]['source_url']==thumb:
            thumb='/'+assets[pid]['path']
        if not thumb:raise RuntimeError('Missing product thumbnail: '+pid)
        public_products.append({k:p.get(k) for k in ('id','name','brand_id','kind','price','sale_price','status','category_ids','type_ids','offers','supplier_status')}|{'image':thumb,'detail_bucket':shard(pid)})
        public_details[shard(pid)][pid]=details[pid]
    counts=Counter(p['brand_id'] for p in public_products)
    kind_counts=Counter((p['brand_id'],p['kind']) for p in public_products)
    for b in brands.values():
        b['aliases']=list(dict.fromkeys(b['aliases']+[alias for alias,key in ALIASES.items() if key==b['id']]))
        b['count']=counts[b['id']]
        b['purchase_count']=kind_counts[(b['id'],'purchase')]
        b['rental_count']=kind_counts[(b['id'],'rental')]
        b['category_ids']=[c['id'] for c in categories.values() if c['brand_id']==b['id']]
    preferred=config.get('brand_order') or ['dji','smallrig','leofoto','tilta','hoya','hy','pgytech','viltrox','nanlite','godox','kupo','aputure','tokina','tokina-cinema','ttartisan','astrhori','wandrd','fxlion','zitay']
    brand_list=sorted(brands.values(),key=lambda b:(preferred.index(b['id']) if b['id'] in preferred else 999,b['name']))
    meta={'schema_version':1,'source_counts':{k:s['product_count'] for k,s in snapshots.items()},'detail_coverage':dict(coverage),
          'synced_at':max(s['collected_at'] for s in snapshots.values()),'merged_count':merge_count,
          'product_count':len(public_products),'category_browsing_enabled':config.get('category_browsing_enabled',False)}
    output={'meta':meta,'brands':brand_list,'categories':list(categories.values()),'products':public_products,'redirects':redirects}
    revision=hashlib.sha256(json.dumps(output,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
    output['meta']['revision']=revision
    PUBLIC.mkdir(parents=True,exist_ok=True)
    for key,bucket in public_details.items():
        (PUBLIC/'details').mkdir(exist_ok=True)
        (PUBLIC/'details'/f'{key}.json').write_text(json.dumps(bucket,ensure_ascii=False,separators=(',',':'))+'\n')
    (PUBLIC/'catalog.json').write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n')
    save_json(PUBLIC/'sync-status.json',meta)
    template=(ROOT/'_scraper/shop_templates/page.html').read_text()
    for filename,title,description,mode in [
      ('index.html','나다운 샵 | 촬영의 모든 장비','DJI, SmallRig, Leofoto 등 촬영장비를 브랜드별로 만나보세요. 카메라·렌즈·조명·삼각대 구매와 렌탈 상담.','home'),
      ('catalog.html','전체 상품 | 나다운 샵','카메라, 렌즈, 조명과 촬영 액세서리. 브랜드와 세부 분류로 나다운 샵의 상품을 찾아보세요.','catalog'),
      ('catalog_category.html','카테고리별 상품 | 나다운 샵','여러 브랜드의 촬영장비를 제품 종류별로 찾아보세요.','categories'),
      ('item.html','상품 상세 | 나다운 샵','나다운 샵 촬영장비의 상품 정보와 이미지를 확인하고 구매 상담을 받아보세요.','item'),
    ]:
        page=template.replace('{{TITLE}}',title).replace('{{DESCRIPTION}}',description).replace('{{CANONICAL}}','https://shop.nadaun.co/'+('' if filename=='index.html' else filename)).replace('{{MODE}}',mode).replace('{{BRAND}}','').replace('{{REVISION}}',revision)
        (ROOT/filename).write_text(page)
    brand_dir=ROOT/'brands';brand_dir.mkdir(exist_ok=True)
    for b in brand_list:
        page=template.replace('{{TITLE}}',html.escape(b['name']+' 브랜드몰 | 나다운 샵')).replace('{{DESCRIPTION}}',html.escape(b['name']+' 촬영장비를 나다운 샵에서 만나보세요. 브랜드별 세부 분류와 상품 정보, 구매 상담.')).replace('{{CANONICAL}}','https://shop.nadaun.co/brands/'+b['id']+'.html').replace('{{MODE}}','catalog').replace('{{BRAND}}',b['id']).replace('{{REVISION}}',revision)
        (brand_dir/(b['id']+'.html')).write_text(page)
    urls=['https://shop.nadaun.co/','https://shop.nadaun.co/catalog.html']+['https://shop.nadaun.co/brands/'+b['id']+'.html' for b in brand_list]
    (ROOT/'catalog-sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+html.escape(u)+'</loc></url>' for u in urls)+'</urlset>\n')
    print(json.dumps(meta,ensure_ascii=False,indent=2))
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--allow-pending',action='store_true');a=p.parse_args();build(a.allow_pending)
