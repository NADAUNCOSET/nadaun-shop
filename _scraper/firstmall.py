# -*- coding: utf-8 -*-
"""Firstmall(가비아 퍼스트몰) 범용 스크래퍼 — avx·오로라몰·사진상사 (2026-07-17, sources.md 자체몰 정찰 결과).
   리스트(/goods/catalog?code=C&page=P&per=40) → 상세(/goods/view?no=N) + 설명(/goods/view_contents?no=N&zoom=1)
   → webp → R2 → 브랜드별 JSON. stable id = <site>-<no>. 증분(R2 skip).
   함정 메모: 가격=JS전역 gl_goods_price(0 초기화 후 재할당→마지막 값), 정가=.consumer_price,
   메인이미지=/data/goods/ 중 <no>_*view.jpg(thumbView 제외), 상세=view_contents의 /data/editor|goods/(skin 제외),
   아이템 링크=display_goods_view('N') onclick(avx·aurora) 또는 href goods/view?no=N(sajin) 둘 다 지원.
   카테고리는 소스 원문(cat_path) 보존 → 최종 분류는 kpp_classify.py.

   실행:
     python firstmall.py <site> NAV | <code> [LIMIT] | ALL [LIMIT]   (체크포인트 data/_<site>_done.json)
   site = avx | aurora | sajin
"""
import sys, io, re, json, time, socket
from pathlib import Path
socket.setdefaulttimeout(60)
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception: pass   # spawn 자식(PIL 프로세스 격리)엔 buffer 없을 수 있음
import requests
from bs4 import BeautifulSoup
from PIL import Image
from brands_map import brand_of

sys.path.insert(0, r"\\Nadaunproject\nadaunproject\_claude\jellyfin_proxy\_r2")
from _r2_common import client, BUCKET
S3 = client()
PUBLIC = "https://media.nadaun.co"
ROOT = Path(r"\\Nadaunproject\nadaunproject\_Site\nadaun-shop")
DATA = ROOT/"data"/"products"; DATA.mkdir(parents=True, exist_ok=True)

SITES = {
 "avx":    {"base":"https://avx.co.kr",         "name":"에이브이엑스"},
 "aurora": {"base":"https://auroramall.co.kr",  "name":"오로라몰"},
 "sajin":  {"base":"https://sajinsangsa.co.kr", "name":"사진상사", "ajax_list":True},  # 짧은 catalog URL엔 상품 안 뜸(2026-07-17 1개 사고) → search_list AJAX
 "green":  {"base":"https://greenshop.co.kr",   "name":"그린촬영시스템", "ajax_list":True},  # 카탈로그가 JS렌더 → search_list AJAX
}

UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36"}
S = requests.Session(); S.headers.update(UA)

import threading
def _fetch_one(u,out):
    try: out.append(S.get(u,timeout=30))
    except Exception as e: out.append(e)

def get(u, retries=3, deadline=50):
    """절대 데드라인 get (scraper-hang-deadline-patterns 2026-07-09)."""
    global S
    for k in range(retries):
        out=[]
        t=threading.Thread(target=_fetch_one,args=(u,out),daemon=True)
        t.start(); t.join(deadline)
        if out and not isinstance(out[0],Exception):
            r=out[0]
            ct=r.headers.get("Content-Type","")
            # chardet 바이너리 함정: 큰 본문에 apparent_encoding 돌리면 메인스레드 수분~수시간 CPU 행
            # (scraper-hang-deadline-patterns / green 209 프리즈 2026-07-18). 1MB 초과면 utf-8 고정.
            if "text" in ct or "html" in ct or "json" in ct:
                r.encoding=(r.apparent_encoding or "utf-8") if len(r.content)<1_000_000 else "utf-8"
            return r
        S=requests.Session(); S.headers.update(UA)
        if k==retries-1: raise RuntimeError(f"get 데드라인 초과/실패: {u}")
        # 하트비트: 서버 tarpit 중 침묵하면 수퍼바이저가 600s 오판kill (스로틀 오판 패턴, green py-spy 2026-07-18)
        print(f"    ! get 재시도 {k+2}/{retries}: {u[:80]}",flush=True)
        time.sleep(10*(k+1))

def _bounded(fn, deadline, *a, **kw):
    out=[]
    def run():
        try: out.append(fn(*a,**kw))
        except Exception as e: out.append(e)
    t=threading.Thread(target=run,daemon=True); t.start(); t.join(deadline)
    if out and not isinstance(out[0],Exception): return out[0]
    raise RuntimeError("R2 op 데드라인/실패")

from concurrent.futures import ProcessPoolExecutor, TimeoutError as _ProcTimeout
_PPOOL=None
def _bounded_proc(fn, deadline, *a, **kw):
    """PIL 등 GIL 잡는 C 연산은 스레드 join으로 못 죽임 → 별도 프로세스 격리+kill (green 209/588 프리즈 2026-07-18)."""
    global _PPOOL
    if _PPOOL is None: _PPOOL=ProcessPoolExecutor(max_workers=1)
    fut=_PPOOL.submit(fn,*a,**kw)
    try: return fut.result(timeout=deadline)
    except _ProcTimeout:
        for p in list(getattr(_PPOOL,"_processes",{}).values()):
            try: p.terminate()
            except Exception: pass
        _PPOOL.shutdown(wait=False); _PPOOL=None
        raise RuntimeError(f"프로세스 데드라인 {deadline}s 초과(kill)")
def clean(t): return re.sub(r"\s+"," ",(t or "").strip())
def price_num(t):
    m=re.findall(r"[\d,]{3,}",clean(t)); return int(m[0].replace(",","")) if m else 0

def absu(base,u):
    if not u: return ""
    u=u.replace("\\","/")
    if u.startswith("//"): return "https:"+u
    if u.startswith("/"): return base+u
    if u.startswith("http"): return u
    return base+"/"+u.lstrip("./")

# ── 카테고리 네비 ───────────────────────────────────────────────
def fetch_nav(base):
    """홈+카탈로그 사이드바에서 code 링크 수집 → {code: name} (godo 2-pass 패턴)."""
    cats={}
    def harvest(soup):
        for a in soup.select('a[href*="/goods/catalog"]'):
            m=re.search(r"code=(\d+)",a.get("href",""))
            if not m: continue
            cid=m.group(1)
            nm=clean(a.get_text())
            if re.fullmatch(r"\d+|[\W_]*",nm or ""): nm=""
            if cid not in cats: cats[cid]=nm
            elif nm and len(cats[cid])<2: cats[cid]=nm
    harvest(BeautifulSoup(get(base+"/").text,"html.parser"))
    for _ in range(2):
        unnamed=[c for c,n in cats.items() if not n]
        if not unnamed: break
        for c in unnamed:
            try: harvest(BeautifulSoup(get(f"{base}/goods/catalog?code={c}").text,"html.parser"))
            except Exception: pass
            time.sleep(0.3)
    for c in cats:
        if not cats[c]: cats[c]=c
    return cats

# ── 리스트 ─────────────────────────────────────────────────────
def list_items(base, code, max_pages=100, ajax=False):
    seen={}
    for page in range(1,max_pages+1):
        if ajax:   # greenshop: 카탈로그 JS렌더 → search_list HTML 프래그먼트
            u=f"{base}/goods/search_list?page={page}&searchMode=catalog&category=c{code}&per=40&auto=1"
        else:
            u=f"{base}/goods/catalog?code={code}&page={page}&per=40"
        html=get(u).text
        got=0
        ids=re.findall(r"display_goods_view\('(\d+)'",html)+re.findall(r"goods/view\?no=(\d+)",html)
        for sid in ids:
            if sid in seen: continue
            seen[sid]=f"{base}/goods/view?no={sid}"; got+=1
        if got==0: break
        if page%10==0: print(f"  … 리스트 수집 p{page} ({len(seen)}개)",flush=True)
        time.sleep(0.4)
    return seen   # {no: url}

# ── 상세 ───────────────────────────────────────────────────────
def parse_item(base, url, site):
    gn=re.search(r"no=(\d+)",url).group(1)
    html=get(url).text
    soup=BeautifulSoup(html,"html.parser")
    og=soup.select_one('meta[property="og:title"]')
    name=clean(og.get("content")) if og and og.get("content") else ""
    if not name or name==SITES[site]["name"]:
        name=clean(soup.title.get_text() if soup.title else "")
        name=re.sub(rf"\s*-\s*{re.escape(SITES[site]['name'])}\s*$","",name)
    # 가격: gl_goods_price 마지막 nonzero (0 초기화 후 재할당), 정가=.consumer_price
    prices=[int(x) for x in re.findall(r"gl_goods_price\s*=\s*(\d+)",html) if int(x)>0]
    salep=prices[-1] if prices else 0
    cel=soup.select_one(".consumer_price")
    listp=price_num(cel.get_text()) if cel else 0
    if listp and salep and listp<salep: listp=0   # 역전 방어
    price=listp or salep
    # 메인: /data/goods/ 중 자기 no_*view (thumbView 제외) + og:image
    def src(i): return absu(base, i.get("src") or i.get("data-src") or "")
    main=[]
    ogimg=soup.select_one('meta[property="og:image"]')
    if ogimg and ogimg.get("content") and f"{gn}_" in ogimg.get("content"): main.append(absu(base,ogimg.get("content")))
    for i in soup.find_all("img"):
        u=src(i)
        if u and "/data/goods/" in u and f"{gn}_" in u and "thumbView" not in u and re.search(r"view\.\w+",u):
            main.append(u)
    if not main:   # view 접미 없으면 자기 no 이미지 전부(thumbView 제외)
        for i in soup.find_all("img"):
            u=src(i)
            if u and "/data/goods/" in u and f"/{gn}_" in u and "thumbView" not in u: main.append(u)
    # 상세설명: view_contents 별도 페이지, /data/editor|goods/ 만 (skin 디자인에셋 제외)
    det=[]
    try:
        cs=BeautifulSoup(get(f"{base}/goods/view_contents?no={gn}&zoom=1").text,"html.parser")
        for i in cs.find_all("img"):
            u=src(i)
            if u and re.search(r"/data/(editor|goods)/",u) and "/data/skin/" not in u: det.append(u)
    except Exception: pass
    det=[d for d in det if not re.search(r"(banner|notice|delivery|benefit|event|as_guide|_cate|guide_)",d.lower())]
    def uniq(xs):
        s=[];[s.append(x) for x in xs if x and x not in s and not x.startswith("data:")];return s
    return {"name":name,"price":price,"list_price":listp,"sale_price":salep,
            "inquiry":price==0,"main":uniq(main),"detail":uniq(det),"url":url}

# ── 이미지 R2 ──────────────────────────────────────────────────
def to_webp(b, maxw, q=82):
    im=Image.open(io.BytesIO(b)).convert("RGB")
    if im.width>maxw: im=im.resize((maxw,int(im.height*maxw/im.width)),Image.LANCZOS)
    o=io.BytesIO(); im.save(o,"WEBP",quality=q,method=6); return o.getvalue()
def r2_exists(key):
    try: _bounded(S3.head_object,20,Bucket=BUCKET,Key=key); return True
    except Exception: return False
def r2_put(key,data):
    _bounded(S3.put_object,60,Bucket=BUCKET,Key=key,Body=data,ContentType="image/webp",
             CacheControl="public,max-age=31536000,immutable")
    return f"{PUBLIC}/{key}"
def upl(src,key,maxw):
    if not src or src.startswith("data:"): return ""
    if r2_exists(key): return f"{PUBLIC}/{key}"
    try:
        r=get(src)   # CT 신뢰 안함(godo CDN multipart 사례)
        if len(r.content)<900 or b"<html" in r.content[:400].lower(): return ""
        data=_bounded_proc(to_webp,120,r.content,maxw)   # PIL 폭탄 이미지 방어 — 프로세스 격리 (green 209/588 프리즈 2026-07-18)
        return r2_put(key,data)
    except Exception as e:
        print(f"    ! 이미지 스킵 {str(src)[:80]}: {e}",flush=True); return ""

# ── 처리 ───────────────────────────────────────────────────────
def process(site, code, cats, limit=None, done_ids=None, ckpt_save=None):
    global S
    S=requests.Session(); S.headers.update(UA)
    base=SITES[site]["base"]; cname=cats.get(code,code)
    items=list_items(base,code,ajax=SITES[site].get("ajax_list",False))
    if done_ids is not None:
        items={sid:u for sid,u in items.items() if sid not in done_ids}
    ids=list(items)[:limit] if limit else list(items)
    print(f"[{SITES[site]['name']}/{cname} · code={code}] 상품 {len(ids)}개")
    by_brand={}
    for i,sid in enumerate(ids,1):
        # per-item 절대 데드라인 240s — 특정 상품 페이지가 파서를 무한정 잡는 결정적 행 방지 (green 209/588 사고 2026-07-17)
        try: d=_bounded(parse_item,240,base,items[sid],site)
        except Exception as e:
            print(f"  ! {sid} 파싱실패/타임아웃(스킵): {e}")
            if done_ids is not None: done_ids.add(sid)   # 재시작 시 같은 상품에서 또 행 걸리지 않게
            continue
        ko,slug=brand_of(d["name"]); pid=f"{site}-{sid}"
        rec={"id":pid,"source":site,"source_id":sid,"name":d["name"],
             "brand":ko,"brand_slug":slug,"category":cname,"cat_path":[cname],
             "cate_no":code,"price":d["price"],"list_price":d["list_price"],
             "sale_price":d["sale_price"],"inquiry":d["inquiry"],
             "source_url":d["url"],"images":{"thumb":"","main":[],"detail":[]}}
        if d["main"]:
            rec["images"]["thumb"]=upl(d["main"][0],f"shop/thumbnails/{slug}/{pid}.webp",600)
        for n,src in enumerate(d["main"],1):
            u=upl(src,f"shop/images/{slug}/{pid}/main_{n}.webp",1600)
            if u: rec["images"]["main"].append(u)
        for n,src in enumerate(d["detail"],1):
            u=upl(src,f"shop/detail/{slug}/{pid}/{n:02d}.webp",1400)
            if u: rec["images"]["detail"].append(u)
            if n%5==0: print(f"    … 이미지 {n}/{len(d['detail'])}",flush=True)
        by_brand.setdefault(slug,{"brand":ko,"brand_slug":slug,"products":{}})
        by_brand[slug]["products"][pid]=rec
        if done_ids is not None: done_ids.add(sid)
        flag="📞" if d["inquiry"] else ""
        print(f"  {i}/{len(ids)} [{ko}] {d['name'][:32]:<32} {d['price']:>9,}{flag}  m{len(rec['images']['main'])} d{len(rec['images']['detail'])}")
        if ckpt_save and i%25==0:
            save(by_brand); by_brand={}   # 부분 저장+체크포인트 — 중간 kill돼도 재시작이 전진 (2026-07-18)
            ckpt_save()
        time.sleep(0.3)
    save(by_brand)
    return by_brand

def save(by_brand):
    for slug,pack in by_brand.items():
        fp=DATA/f"{slug}.json"
        if fp.exists():
            old=json.load(open(fp,encoding="utf-8"))
            old.setdefault("products",{}).update(pack["products"])
            old["brand"]=pack["brand"]; old["brand_slug"]=slug; pack=old
        json.dump(pack,open(fp,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
        print(f"  → data/products/{slug}.json ({len(pack['products'])}개)")

if __name__=="__main__":
    if len(sys.argv)<3 or sys.argv[1] not in SITES:
        print("사용법: python firstmall.py <site> NAV|ALL|<code> [LIMIT]"); print("site =", " | ".join(SITES)); sys.exit(1)
    site=sys.argv[1]; arg=sys.argv[2]; base=SITES[site]["base"]
    cats=fetch_nav(base)
    if arg=="NAV":
        print(f"[{SITES[site]['name']}] 카테고리 {len(cats)}개")
        for c,n in sorted(cats.items()): print(f"  {c:<14} {n}")
    elif arg=="ALL":
        lim=int(sys.argv[3]) if len(sys.argv)>3 else None
        ckpt=DATA.parent/f"_{site}_done.json"
        st=json.load(open(ckpt,encoding="utf-8")) if ckpt.exists() else {"cats":[],"ids":[]}
        if isinstance(st,list): st={"cats":st,"ids":[]}
        done_set=set(st["cats"]); done_ids=set(st["ids"])
        SKIP_CAT=("개인결제","상품명","고객결제")
        todo=[c for c in sorted(cats) if not any(s in cats[c] for s in SKIP_CAT)]; tot={}
        print(f"=== {SITES[site]['name']} 전체 스크랩: 카테고리 {len(todo)}개 (완료스킵 {len(done_set)}, 상품스킵 {len(done_ids)}) ===",flush=True)
        ckpt_save=lambda: json.dump({"cats":sorted(done_set),"ids":sorted(done_ids)},open(ckpt,"w",encoding="utf-8"))
        for k,c in enumerate(todo,1):
            if c in done_set: continue
            try:
                bb=process(site,c,cats,lim,done_ids,ckpt_save)
                for s in bb: tot[s]=tot.get(s,0)+len(bb[s]["products"])
                done_set.add(c)
                json.dump({"cats":sorted(done_set),"ids":sorted(done_ids)},open(ckpt,"w",encoding="utf-8"))
            except Exception as e:
                print(f"  !! 카테고리 {c} 실패(스킵): {e}",flush=True)
            print(f"--- 진행 {k}/{len(todo)}, 누계 {sum(tot.values())} ---",flush=True)
        print("\n=== 완료 브랜드별 누계 ===",flush=True)
        for s,n in sorted(tot.items(),key=lambda x:-x[1]): print(f"  {s:<14} {n}",flush=True)
    else:
        lim=int(sys.argv[3]) if len(sys.argv)>3 else None
        process(site,arg,cats,lim)
