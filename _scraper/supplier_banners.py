"""Archive observed supplier banner originals and maintain the private review HTML.

No image resizing, supplier writes, merchant links in public shop banners, or
automatic approval. Access holds are checked before either pages or assets.
"""
from pathlib import Path
from urllib.parse import urljoin,urlsplit,quote
import argparse,datetime,hashlib,html,io,json,os,re,time
import requests
from bs4 import BeautifulSoup
from PIL import Image
from mirror_schedule import ROOT,atomic_json,controls,policy,timestamp

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def image_candidates(body,url):
    doc=BeautifulSoup(body,'lxml');result={}
    def add(value,context,rank=0,label='',href=''):
        absolute=urljoin(url,value.strip())
        parsed=urlsplit(absolute)
        if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username:return
        if re.search(r'(?:logo|icon|btn_|button|sns|favicon|spinner)',parsed.path,re.I):return
        if not context and not re.search(r'banner|main_visual|mainvisual|slide|rolling|popup|promotion',absolute,re.I):return
        old=result.get(absolute)
        row={'url':absolute,'label':label.strip(),'source_target':urljoin(url,href) if href else '',
             'candidate_rank':rank,'selection_basis':'largest explicitly observed src/srcset or banner CSS image; no URL guessed'}
        if not old or old['candidate_rank']<rank:result[absolute]=row
    for img in doc.select('img'):
        ancestors=list(img.parents)[:5]
        tags=' '.join(str(x.get('id',''))+' '+' '.join(x.get('class',[])) for x in [img,*ancestors])
        context=bool(re.search(r'banner|main.?visual|slider|rolling|slide|promotion|event.?visual',tags,re.I))
        if re.search(r'prdList|product-list|listnormal|goods_list|product-card',tags,re.I) and not re.search(r'banner|main.?visual',tags,re.I):continue
        label=img.get('alt','');anchor=img.find_parent('a');href=anchor.get('href','') if anchor else ''
        choices=[]
        for key,rank in [('src',0),('data-src',1),('data-lazy-src',1),('data-original',1000000000)]:
            if img.get(key):choices.append((rank,img[key]))
        for key in ('srcset','data-srcset'):
            for part in img.get(key,'').split(','):
                bits=part.strip().split()
                if bits:
                    match=re.fullmatch(r'([\d.]+)(w|x)',bits[-1]);rank=float(match[1])*(10000 if match[2]=='x' else 1) if match else 0
                    choices.append((rank,bits[0]))
        if choices:
            rank,value=max(choices,key=lambda c:c[0]);add(value,context,rank,label,href)
        picture=img.find_parent('picture')
        if picture:
            for source in picture.select('source[srcset]'):
                choices=[]
                for part in source['srcset'].split(','):
                    bits=part.strip().split()
                    if bits:choices.append((float(re.sub(r'[^\d.]','',bits[-1]) or 0) if len(bits)>1 else 0,bits[0]))
                if choices:
                    rank,value=max(choices);add(value,context,rank,label,href)
    for tag in doc.select('[style]'):
        context=bool(re.search(r'banner|visual|slide|rolling|promotion',' '.join(tag.get('class',[]))+' '+str(tag.get('id','')),re.I))
        for value in re.findall(r'url\([\s\"\']*([^\)\"\']+)',tag['style']):add(value,context)
    # Divi provides homepage visual originals in inline stylesheet rules.
    # The selector must identify an element actually present in this page.
    for style in doc.select('style'):
        for selector,body in re.findall(r'([^{}]+)\{([^{}]*background-image\s*:[^{}]*)\}',style.get_text()):
            if not re.search(r'\.et_pb_(?:row|column|slide)_\d+',selector):continue
            simple=re.search(r'\.et_pb_(?:row|column|slide)_\d+',selector)[0]
            if not doc.select_one(simple):continue
            for value in re.findall(r'url\([\s\"\']*([^\)\"\']+)',body):add(value,True)
    return list(result.values())

def decode(raw):
    with Image.open(io.BytesIO(raw)) as img:
        fmt=img.format;size=img.size;frames=getattr(img,'n_frames',1)
        if fmt not in ('JPEG','PNG','WEBP','GIF','AVIF'):raise ValueError('Unsupported banner image type')
        if size[0]*size[1]>80000000 or frames>1200:raise ValueError('Oversized image requires separate review')
        for frame in range(frames):img.seek(frame);img.load()
    return {'format':fmt,'width':size[0],'height':size[1],'frames':frames}

class Fetcher:
    def __init__(self,delay=5):
        self.session=requests.Session();self.session.headers['User-Agent']='NADAUNShopBannerArchive/1.0'
        self.delay=delay;self.last={}
    def get(self,url):
        host=urlsplit(url).netloc;time.sleep(max(0,self.delay-(time.monotonic()-self.last.get(host,0))))
        self.last[host]=time.monotonic();response=self.session.get(url,timeout=(8,35),allow_redirects=False)
        if response.status_code in (301,302,307,308):
            target=urljoin(url,response.headers.get('Location',''));a=urlsplit(url);b=urlsplit(target)
            if b.hostname and a.hostname.removeprefix('www.')==b.hostname.removeprefix('www.') and b.scheme in ('https','http'):
                response=self.session.get(target,timeout=(8,35),allow_redirects=False)
        return response

def render(root,manifest):
    out=Path(root).resolve()/'검토자료/13_공급처배너';out.mkdir(parents=True,exist_ok=True)
    cards=[]
    for row in manifest['assets']:
        uri=quote(os.path.relpath(Path(row['path']).resolve(),out).replace(os.sep,'/'),safe='/')
        caption=html.escape(row.get('label') or Path(urlsplit(row['url']).path).name)
        if row.get('current') is False:caption='이전 버전 보존 · '+caption
        cards.append('<article data-source="'+html.escape(row['source'],quote=True)+'"><img loading="lazy" src="'+html.escape(uri,quote=True)+'" alt="'+caption+'"><p><b>'+html.escape(row['source'])+'</b> · '+str(row['width'])+'×'+str(row['height'])+' · '+str(row['frames'])+'프레임</p><p>'+caption+'</p><small>'+html.escape(row['review_state'])+'</small><p><a href="'+html.escape(row['url'],quote=True)+'" target="_blank" rel="noopener">제공 원본</a> · <a href="'+html.escape(uri,quote=True)+'">NAS 원본</a></p></article>')
    statuses=''.join('<tr><td>'+html.escape(s['source'])+'</td><td>'+html.escape(s['state'])+'</td><td>'+html.escape(s.get('reason',''))+'</td><td>'+str(s.get('saved_assets',0))+'</td></tr>' for s in manifest['sites'])
    page='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>공급처 배너 원본 검토</title><style>body{margin:0;background:#f5f5f2;color:#202925;font:15px/1.65 Pretendard,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}header,main{max-width:1500px;margin:auto;padding:24px}header{background:#fff}h1{font-size:28px}a{color:#17635c}.notice{padding:16px;background:#fff4d7;border:1px solid #dcccab}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:18px}article{padding:15px;background:white;border:1px solid #ddd;min-width:0}img{width:100%;height:230px;object-fit:contain;background:#edf0ec}small{color:#7b5014}table{width:100%;border-collapse:collapse;margin:20px 0}td,th{text-align:left;padding:10px;border-bottom:1px solid #ddd}input{font:inherit;padding:10px;width:min(500px,90%);margin:16px 0}</style><header><a href="../00_여기서_시작.html">전체 검토자료</a><h1>공급처 배너 · 제공 원본 모음</h1><p>UPDATE · COUNT개 원본</p><p class="notice">다운로드 원본은 축소·재압축하지 않았습니다. 상품·제조사·행사 배너를 검토할 자료이며 공개 게시 승인이 아닙니다. 다른 판매점 구매/전화/방문 유도, 만료 행사·조건 불명 가격, 취급 제외 브랜드는 확인 후 제외합니다. 원본 링크는 내부 검토용이며 우리 쇼핑몰 배너의 이동 링크로 사용하지 않습니다. Mac과 NAS 연결이 필요합니다.</p></header><main><h2>사이트 확인 내역</h2><table><thead><tr><th>사이트</th><th>확인 상태</th><th>보류·오류</th><th>원본</th></tr></thead><tbody>STATUS</tbody></table><h2>원본 배너</h2><input id="q" placeholder="사이트·파일명·문구 검색"><section>CARDS</section><script>document.getElementById('q').oninput=e=>{const q=e.target.value.toLowerCase();for(const c of document.querySelectorAll('article'))c.hidden=!c.textContent.toLowerCase().includes(q)}</script></main></html>'''
    page=page.replace('Mac과 NAS 연결이 필요합니다.','NAS 원본 폴더 연결이 필요합니다.')
    page=page.replace('UPDATE',html.escape(manifest['checked_at'])).replace('COUNT',str(len(manifest['assets']))).replace('STATUS',statuses).replace('CARDS',''.join(cards))
    target=out/'00_전체배너_검토.html';target.write_text(page)
    atomic_json(out/'배너_원본_검토목록.json',manifest)
    return target

def collect(root=ROOT,sources=None,force=False,limit=80,fetcher=None):
    root=Path(root).resolve();settings=policy(root);state=root/'_private/catalog/supplier-banners';state.mkdir(parents=True,exist_ok=True)
    pointer=state/'current.json';old=json.loads(pointer.read_text()) if pointer.exists() else {}
    plan=json.loads((root/'_scraper/partner-sync-plan.json').read_text())['sources'];fetcher=fetcher or Fetcher()
    sites={s['source']:s for s in old.get('sites',[])}
    manifest={'schema_version':1,'checked_at':now(),'assets':list(old.get('assets',[])),'sites':list(sites.values()),'public_posting_approved':False}
    def save(row):
        sites[row['source']]=row;manifest['sites']=list(sites.values());atomic_json(pointer,manifest)
    known={row['url']:row for row in manifest['assets']};digest_paths={row['sha256']:row['path'] for row in manifest['assets']}
    for source,config in plan.items():
        if sources and source not in sources:continue
        checked=timestamp(sites.get(source,{}).get('checked_at'))
        if not force and checked is not None and 0<=time.time()-checked<settings['refresh_interval_seconds']:continue
        hold=controls(source,root);row={'source':source,'url':config['url'],'checked_at':now(),'state':'checking','saved_assets':0}
        if (state/(source+'-access-hold.json')).exists():hold={'blocked':True,'phase':'banner_access_held','reason':'Existing banner access-protection hold; no automatic retry'}
        if source=='smartstore':hold={'blocked':True,'phase':'api_catalog_only','reason':'Smartstore product access uses the existing merchant read API; no public-page retry'}
        if hold.get('blocked'):
            row.update(state=hold['phase'],reason=hold.get('reason',''));save(row);continue
        try:
            response=fetcher.get(config['url']);row['http_status']=response.status_code
            if response.status_code in (401,403,429):
                row.update(state='access_held',reason='Protection response; no automatic retry or alternate route')
                atomic_json(state/(source+'-access-hold.json'),row);save(row);continue
            if response.status_code!=200:raise ValueError('Homepage HTTP '+str(response.status_code))
            body=response.content;pages=state/'pages';pages.mkdir(exist_ok=True);sha=hashlib.sha256(body).hexdigest();(pages/(source+'-'+sha[:16]+'.html')).write_bytes(body)
            row.update(state='homepage_checked',page_sha256=sha)
            for item in image_candidates(body,response.url)[:limit]:
                # Suppliers often overwrite an image at the same URL. A prior
                # URL observation must not bypass the next five-day read.
                image_response=fetcher.get(item['url'])
                if image_response.status_code in (401,403,429):
                    row['reason']='Banner asset protection response; remaining assets preserved for review'
                    atomic_json(state/(source+'-access-hold.json'),{'at':now(),'status':image_response.status_code,'url':item['url'],'automatic_resume':False});break
                if image_response.status_code!=200:continue
                data=image_response.content
                if not data or len(data)>25*1024*1024:continue
                try:meta=decode(data)
                except (OSError,ValueError,Image.DecompressionBombError):continue
                if meta['width']<480 or meta['height']<90 or not .65<=meta['width']/meta['height']<=12:continue
                digest=hashlib.sha256(data).hexdigest();ext={'JPEG':'jpg','PNG':'png','WEBP':'webp','GIF':'gif','AVIF':'avif'}[meta['format']]
                target=Path(digest_paths.get(digest,state/'assets'/(digest+'.'+ext)));target.parent.mkdir(parents=True,exist_ok=True)
                if not target.exists():target.write_bytes(data)
                if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise ValueError('Banner archive hash mismatch')
                result={**item,**meta,'source':source,'source_page':response.url,'observed_at':now(),'sha256':digest,'bytes':len(data),'path':str(target.resolve()),'review_state':'검토 대기 · 판매점 유도·행사 기간·우리 상품 연결 확인 필요','quality_verified':'Largest observed candidate; original bytes fully decoded and SHA checked'}
                previous=known.get(item['url'])
                if previous and previous['sha256']==digest:previous.update(result,current=True)
                else:
                    if previous:previous['current']=False;result['supersedes_sha256']=previous['sha256']
                    result['current']=True;manifest['assets'].append(result);known[item['url']]=result
                digest_paths[digest]=str(target);row['saved_assets']+=1;atomic_json(pointer,manifest)
            row['state']='homepage_and_banner_archive_checked'
        except Exception as exc:row.update(state='requires_review',reason=type(exc).__name__+': '+str(exc)[:300])
        save(row);render(root,manifest)
        print(source,row['state'],row['saved_assets'],flush=True)
    manifest['finished_at']=now();atomic_json(pointer,manifest);render(root,manifest)
    return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--force',action='store_true');parser.add_argument('--source',action='append');parser.add_argument('--limit',type=int,default=80);args=parser.parse_args()
    result=collect(args.root,args.source,args.force,args.limit);print(json.dumps({'assets':len(result['assets']),'sites':len(result['sites'])},ensure_ascii=False))
