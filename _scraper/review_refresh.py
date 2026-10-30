"""Refresh the operator's NAS product-review HTML after every publication.

No supplier/own-site requests, policy inference, browser opening, or Excel
overwrite. Existing review notes are preserved by the normal NAS generators.
"""
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import hashlib,html,json,re,subprocess,sys,tarfile,io,os
from mirror_schedule import ROOT,atomic_json

DATA=re.compile(r'(<script\b[^>]*\bid=["\'](?:review-)?data["\'][^>]*>)([\s\S]*?)(</script>)')
def load(path):return json.loads(Path(path).read_text())
def replace_payload(path,payload):
    path=Path(path);page=path.read_text();match=DATA.search(page)
    if not match or 'application/json' not in match[1]:raise ValueError('Review template payload missing: '+path.name)
    packed=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    page=page[:match.start(2)]+packed+page[match.end(2):]
    temporary=path.with_name('.'+path.name+'.pending');temporary.write_text(page);os.replace(temporary,path)

def category_payload(catalog):
    categories={c['id']:c for c in catalog['categories']}
    def trail(cid):
        values=[];seen=set()
        while cid:
            if cid in seen or cid not in categories:raise ValueError('Review category ancestry is invalid')
            seen.add(cid);row=categories[cid];values.insert(0,row['name']);cid=row.get('parent_id')
        return ' > '.join(values)
    products=[]
    for p in catalog['products']:
        parents={categories[c].get('parent_id') for c in p['category_ids']}
        products.append({'id':p['id'],'listing':p.get('listing_id',p['id']),'name':p['name'],'brand':p['brand_id'],'kind':p['kind'],
            'types':p['type_ids'],'categories':p.get('navigation_category_ids',p['category_ids']),
            'native':[trail(c) for c in p['category_ids'] if c not in parents],
            'sources':sorted({o['source'] for o in p['offers']}),'urls':[o['url'] for o in p['offers']]})
    return {'at':datetime.now(timezone.utc).isoformat(),'revision':catalog['meta']['revision'],
        'brands':[{k:b[k] for k in ('id','name','aliases')} for b in catalog['brands']],
        'categories':catalog['categories'],'products':products,'source_access':'saved_publication_only','live_ui_verified':False}

def content_payload(root,catalog,old,publication):
    products={p['id']:p for p in catalog['products']};brands={b['id']:b['name'] for b in catalog['brands']};models={m['id']:m for m in catalog['camera_models']}
    retail=load(root/'_private/catalog/retail-content-review.json');changes={r['id']:r for r in retail['products']}
    compat=load(root/'_private/catalog/camera-compatibility-review.json');tables=old['tables']
    url=lambda pid:'https://shop.nadaun.co/item.html?id='+pid
    tables['타 업체 안내 제외내역']=[{'id':pid,'brand':brands[p['brand_id']],'name':p['name'],'state':'타 판매점 안내 제외','detail':' · '.join(dict.fromkeys(x.get('reason','') for x in r['changes'] if x.get('reason'))),'url':url(pid)} for pid,r in changes.items() if (p:=products.get(pid))]
    tables['카메라별 액세서리']=[{'id':mid+'|'+pid,'brand':brands[products[pid]['brand_id']],'name':products[pid]['name'],'state':m['name']+' 전용','detail':'같은 제품에 연결된 원본 상품명에 기종 명시 · 옵션/세대 확인','url':url(pid)} for mid,m in models.items() for pid in m['accessory_product_ids']]
    tables['카메라 본체 연결']=[{'id':mid+'|'+pid,'brand':brands[products[pid]['brand_id']],'name':products[pid]['name'],'state':m['name'],'detail':str(len(m['accessory_product_ids']))+'개 액세서리 연결','url':url(pid)} for mid,m in models.items() for pid in m['camera_product_ids']]
    tables['전체 상품 점검']=[{'id':pid,'brand':brands[p['brand_id']],'name':p['name'],'state':'대여 원장 유지' if p['kind']=='rental' else '타 판매점 안내 제외' if pid in changes else '텍스트·등록된 광고 규칙 검사','detail':' · '.join(models[mid]['name'] for mid in p.get('camera_model_ids',[])+p.get('compatible_camera_model_ids',[])) or '개별 이미지의 모든 문구까지 확인했다는 뜻은 아닙니다.','url':url(pid)} for pid,p in products.items()]
    old.update(revision=catalog['meta']['revision'],model_count=len(models),associations=len(compat['associations']),products=len(products),changed=len(changes),created_at=datetime.now(timezone.utc).isoformat(),publication=publication.get('commit'),deployment=publication.get('deployment'))
    return old

def refresh(root=ROOT,publication=None):
    root=Path(root).resolve();stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder=root/'_private/catalog/review-refresh-runs'/stamp;folder.mkdir(parents=True)
    publication=publication or {};result={'checked_at':datetime.now(timezone.utc).isoformat(),'passed':False,'own_site_requests':0,'supplier_requests':0,'browser_ui_verified':False}
    main=root/'검토자료/00_여기서_시작.html';nine=root/'검토자료/09_브랜드와상세분류/00_브랜드와제품종류_전체검토.html';ten=root/'검토자료/10_상세정리와호환모델/00_상세와호환모델_전체검토.html';eleven=root/'검토자료/11_중복상품과공급처선택/00_겹치는상품_공급처비교.html'
    progress=ten.parent/'01_현재진행상태.md'
    paths=[main,nine,ten,eleven,root/'검토자료/_관리/review-data.json',progress];sha={}
    try:
        cat=load(root/'data/catalog/catalog.json');revision=cat['meta']['revision'];reg=load(root/'_private/catalog/brand-source-register.json')
        if reg['revision']!=revision or publication.get('revision',revision)!=revision:raise ValueError('Published catalogue and review audit revision differ')
        result['revision']=revision
        with tarfile.open(folder/'before.tar.gz','w:gz',compresslevel=1) as tar:
            for path in paths:
                data=path.read_bytes();name=path.relative_to(root).as_posix();sha[name]=hashlib.sha256(data).hexdigest();info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
        with tarfile.open(folder/'before.tar.gz') as tar:
            for name,digest in sha.items():
                if hashlib.sha256(tar.extractfile(name).read()).hexdigest()!=digest:raise ValueError('Review backup readback differs')
        proof=load(root/'_private/catalog/category-dedup-review.json');proof.update(revision=revision,publication_commit=publication.get('commit'),publication_state='published_review_refresh')
        atomic_json(root/'_private/catalog/category-dedup-review.json',proof)
        manager=root/'검토자료/_관리'
        for name,args in [('saved-tables',[sys.executable,str(manager/'refresh_saved_review.py')]),('main-html',['node',str(manager/'refresh_review_page.mjs')])]:
            with (folder/(name+'.log')).open('w') as log:subprocess.run(args,cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1200)
        payload=category_payload(cat);replace_payload(nine,payload);atomic_json(nine.parent/'20261027_전체분류_원장.json',payload)
        old=load_payload(ten);replace_payload(ten,content_payload(root,cat,old,publication))
        with (folder/'overlap.log').open('w') as log:subprocess.run([sys.executable,str(manager/'build_overlap_review.py')],cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        # Compile generated inline JavaScript before a successful receipt.
        check="const fs=require('fs'),vm=require('vm');for(const p of process.argv.slice(1)){const h=fs.readFileSync(p,'utf8');for(const s of h.matchAll(/<script([^>]*)>([\\s\\S]*?)<\\/script>/g)){if(s[1].includes('application/json'))JSON.parse(s[2]);else if(!/src=/.test(s[1]))new vm.Script(s[2]);}}"
        subprocess.run(['node','-e',check,*map(str,[main,nine,ten,eleven])],check=True,cwd=root,capture_output=True,timeout=60)
        for path in [main,nine,ten,eleven]:
            data=load_payload(path)
            if (data.get('revision') or data.get('evidence',{}).get('revision'))!=revision:raise ValueError('Review HTML revisions differ')
        start='<!-- AUTO-REVIEW-CURRENT BEGIN -->';end='<!-- AUTO-REVIEW-CURRENT END -->'
        text=progress.read_text();text=re.sub(re.escape(start)+r'[\s\S]*?'+re.escape(end)+r'\n*','',text)
        current=(start+'\n## 최신 검토자료 갱신\n\n'+result['checked_at']+' · revision `'+revision+'`\n\n'
            +f"전체 {len(cat['products']):,}상품·{len(cat['brands'])}브랜드·{len(cat['categories']):,}분류의 검토 HTML 4개를 같은 저장 배포본으로 갱신했습니다. 원본 최신 전수 대조·로그인·주문결제·브라우저 UI를 이번 작업에서 새 검증했다는 뜻은 아닙니다.\n\n"
            +'[5일 자동 미러링·사이트별 현재 상태](../14_자동미러링/00_사이트별_자동미러링.html) · [공급처 배너 원본](../13_공급처배너/00_전체배너_검토.html)\n'+end+'\n\n')
        progress.write_text(current+text)
        result.update(passed=True,products=len(cat['products']),brands=len(cat['brands']),categories=len(cat['categories']),html_files=4,backup_verified=True,notes='Normal generators preserve owner notes by row ID; existing Excel is unchanged')
    except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)
    result['receipt']=str((folder/'receipt.json').relative_to(root));atomic_json(folder/'receipt.json',result);atomic_json(root/'_private/catalog/review-refresh-latest.json',result)
    return result

def load_payload(path):
    match=DATA.search(Path(path).read_text())
    if not match:raise ValueError('Missing review JSON')
    return json.loads(match[2])

if __name__=='__main__':
    result=refresh();print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if result['passed'] else 2)
