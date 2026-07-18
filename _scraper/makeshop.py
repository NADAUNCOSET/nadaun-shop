# -*- coding: utf-8 -*-
"""MakeShop 스크래퍼 — 유쾌한생각 plthink.com (2026-07-17, sources.md 참조. cafe24/godo 패턴).
   리스트(/shop/shopbrand.html?type=T&xcode=X&mcode=M&page=P) → 상세(shopdetail.html?branduid=N)
   → 정가 캡처 → webp → R2 → 브랜드별 JSON. stable id = plthink-<branduid>. 증분(R2 skip).
   함정 메모: og:image=범용 로고(무시), 메인=.thumb img, 상세=.ck-content img, .prd-img=관련상품(제외).
   카테고리는 소스 원문(cat_path) 보존 → 최종 분류는 kpp_classify.py (KPP 택소노미 SoT).

   실행:
     python makeshop.py plthink NAV                 # 카테고리 덤프
     python makeshop.py plthink <xcode-mcode> [LIMIT]  # 파일럿 (예: 008-002)
     python makeshop.py plthink ALL [LIMIT]         # 전 카테고리 (체크포인트 data/_plthink_done.json)
"""
import sys, io, re, json, time, socket
from pathlib import Path
socket.setdefaulttimeout(60)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
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
 "plthink": {"base":"https://www.plthink.com", "name":"유쾌한생각"},
}
SITE_PREFIX = {"plthink":"유쾌한생각"}   # og:title "사이트명 - 상품명" 접두 제거용

UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36"}
S = requests.Session(); S.headers.update(UA)

import threading
def _fetch_one(u,out):
    try: out.append(S.get(u,timeout=30))
    except Exception as e: out.append(e)

def get(u, retries=3, deadline=50):
    """절대 데드라인 get — 타르핏 드립피드 대응 (scraper-hang-deadline-patterns 2026-07-09)."""
    global S
    for k in range(retries):
        out=[]
        t=threading.Thread(target=_fetch_one,args=(u,out),daemon=True)
        t.start(); t.join(deadline)
        if out and not isinstance(out[0],Exception):
            r=out[0]
            ct=r.headers.get("Content-Type","")
            if "text" in ct or "html" in ct or "json" in ct:
                r.encoding=r.apparent_encoding or "utf-8"
            return r
        S=requests.Session(); S.headers.update(UA)
        if k==retries-1: raise RuntimeError(f"get 데드라인 초과/실패: {u}")
        time.sleep(2*(k+1))

def _bounded(fn, deadline, *a, **kw):
    out=[]
    def run():
        try: out.append(fn(*a,**kw))
        except Exception as e: out.append(e)
    t=threading.Thread(target=run,daemon=True); t.start(); t.join(deadline)
    if out and not isinstance(out[0],Exception): return out[0]
    raise RuntimeError("R2 op 데드라인/실패")
def clean(t): return re.sub(r"\s+"," ",(t or "").strip())
def price_num(t):
    m=re.findall(r"[\d,]{3,}",clean(t)); return int(m[0].replace(",","")) if m else 0

def absu(base,u):
    if not u: return ""
    u=u.replace("\\","/")
    u=re.sub(r"^https?://(https?://)",r"\1",u)   # 사이트 데이터 오류: http://https://... 이중 스킴 정리 (008-131)
    if u.startswith("//"): return "https:"+u
    if u.startswith("/"): return base+u
    if u.startswith("http"): return u
    return base+"/"+u.lstrip("./")

# ── 카테고리 네비 ───────────────────────────────────────────────
def fetch_nav(base):
    """홈+대분류 페이지에서 shopbrand 링크 수집 → {"xcode-mcode": {"href":..., "name":...}}.
       홈 메뉴에 안 뜨는 중분류가 있어 2-pass: 각 대분류(xcode) 페이지 사이드바에서 보충 (2026-07-17)."""
    cats={}
    def harvest(soup):
        for a in soup.select('a[href*="shopbrand.html"]'):
            href=a.get("href","")
            mx=re.search(r"xcode=(\d+)",href)
            if not mx: continue
            mm=re.search(r"mcode=(\d+)",href)
            key=mx.group(1)+("-"+mm.group(1) if mm else "")
            nm=clean(a.get_text())
            if re.fullmatch(r"\d+|[\W_]*",nm or ""): nm=""   # 페이지네이션/기호 링크 제외
            if key not in cats: cats[key]={"href":href,"name":nm}
            elif nm and len(cats[key]["name"])<2: cats[key]["name"]=nm
    harvest(BeautifulSoup(get(base+"/").text,"html.parser"))
    for top in [k for k in list(cats) if "-" not in k]:
        try: harvest(BeautifulSoup(get(absu(base,cats[top]["href"])).text,"html.parser"))
        except Exception: pass
        time.sleep(0.3)
    for k in cats:
        if not cats[k]["name"]: cats[k]["name"]=k
    return cats

# ── 리스트 ─────────────────────────────────────────────────────
def list_items(base, href, max_pages=100):
    seen={}
    sep="&" if "?" in href else "?"
    for page in range(1,max_pages+1):
        u=absu(base,href)+f"{sep}page={page}"
        soup=BeautifulSoup(get(u).text,"html.parser")
        got=0
        for a in soup.select('a[href*="shopdetail.html"]'):
            m=re.search(r"branduid=(\d+)",a.get("href",""))
            if not m: continue
            sid=m.group(1)
            if sid in seen: continue
            seen[sid]=f"{base}/shop/shopdetail.html?branduid={sid}"; got+=1
        if got==0: break
        if page%10==0: print(f"  … 리스트 수집 p{page} ({len(seen)}개)",flush=True)
        time.sleep(0.4)
    return seen   # {branduid: url}

# ── 상세 ───────────────────────────────────────────────────────
def parse_item(base, url, site):
    soup=BeautifulSoup(get(url).text,"html.parser")
    og=soup.select_one('meta[property="og:title"]')
    name=clean(og.get("content")) if og and og.get("content") else clean(soup.title.get_text() if soup.title else "")
    name=re.sub(rf"^{re.escape(SITE_PREFIX[site])}\s*-\s*","",name)
    # 정가(소비자가) 우선, 없으면 판매가 — 라벨 행 스캔
    listp=salep=0
    for row in soup.select("tr, li, dl, div.price-row"):
        lab=row.find(["th","dt","strong","span"])
        if not lab: continue
        lt=clean(lab.get_text())
        if lt not in ("정가","소비자가","판매가"): continue
        val=price_num(row.get_text().replace(lt,"",1))
        if not val: continue
        if lt in ("정가","소비자가") and not listp: listp=val
        elif lt=="판매가" and not salep: salep=val
    price=listp or salep
    def src(i): return absu(base, i.get("src") or i.get("data-src") or "")
    # 메인 = .thumb img (og:image는 범용 로고라 무시), 관련상품 .prd-img 제외
    main=[]
    for i in soup.select(".thumb img, .thumb-wrap img, #productDetail .thumb img"):
        u=src(i)
        if u and "shopimages" in u and "scrap" not in u: main.append(u)
    # 상세설명 = .ck-content img (에디터 본문)
    det=[]
    for i in soup.select(".ck-content img, #productDetail .cont img, .prd-detail img"):
        u=src(i)
        if u: det.append(u)
    det=[d for d in det if not re.search(r"(banner|notice|delivery|benefit|event|as_guide|_cate|guide_|all_common)",d.lower())]
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
        r=get(src)   # CT 신뢰 안함(godo CDN multipart 사례) — 디코딩으로 판정
        if len(r.content)<900 or b"<html" in r.content[:400].lower(): return ""
        data=_bounded(to_webp,120,r.content,maxw)   # PIL 폭탄 이미지 방어
        return r2_put(key,data)
    except Exception: return ""

# ── 처리 ───────────────────────────────────────────────────────
def process(site, key, cats, limit=None, done_ids=None):
    global S
    S=requests.Session(); S.headers.update(UA)
    base=SITES[site]["base"]; c=cats[key]; cname=c["name"]
    items=list_items(base,c["href"])
    if done_ids is not None:
        items={sid:u for sid,u in items.items() if sid not in done_ids}
    ids=list(items)[:limit] if limit else list(items)
    print(f"[{SITES[site]['name']}/{cname} · {key}] 상품 {len(ids)}개")
    by_brand={}
    for i,sid in enumerate(ids,1):
        try: d=parse_item(base,items[sid],site)
        except Exception as e: print(f"  ! {sid} 파싱실패 {e}"); continue
        ko,slug=brand_of(d["name"]); pid=f"{site}-{sid}"
        rec={"id":pid,"source":site,"source_id":sid,"name":d["name"],
             "brand":ko,"brand_slug":slug,"category":cname,"cat_path":[cname],
             "cate_no":key,"price":d["price"],"list_price":d["list_price"],
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
        print("사용법: python makeshop.py <site> NAV|ALL|<xcode-mcode> [LIMIT]"); print("site =", " | ".join(SITES)); sys.exit(1)
    site=sys.argv[1]; arg=sys.argv[2]; base=SITES[site]["base"]
    cats=fetch_nav(base)
    if arg=="NAV":
        print(f"[{SITES[site]['name']}] 카테고리 {len(cats)}개")
        for k in sorted(cats): print(f"  {k:<10} {cats[k]['name']}")
    elif arg=="ALL":
        lim=int(sys.argv[3]) if len(sys.argv)>3 else None
        ckpt=DATA.parent/f"_{site}_done.json"
        st=json.load(open(ckpt,encoding="utf-8")) if ckpt.exists() else {"cats":[],"ids":[]}
        done_set=set(st["cats"]); done_ids=set(st["ids"])
        SKIP_CAT=("개인결제","상품명","고객결제")
        todo=[k for k in sorted(cats) if not any(s in cats[k]["name"] for s in SKIP_CAT)]; tot={}
        print(f"=== {SITES[site]['name']} 전체 스크랩: 카테고리 {len(todo)}개 (완료스킵 {len(done_set)}, 상품스킵 {len(done_ids)}) ===",flush=True)
        for k2,key in enumerate(todo,1):
            if key in done_set: continue
            try:
                bb=process(site,key,cats,lim,done_ids)
                for s in bb: tot[s]=tot.get(s,0)+len(bb[s]["products"])
                done_set.add(key)
                json.dump({"cats":sorted(done_set),"ids":sorted(done_ids)},open(ckpt,"w",encoding="utf-8"))
            except Exception as e:
                print(f"  !! 카테고리 {key} 실패(스킵): {e}",flush=True)
            print(f"--- 진행 {k2}/{len(todo)}, 누계 {sum(tot.values())} ---",flush=True)
        print("\n=== 완료 브랜드별 누계 ===",flush=True)
        for s,n in sorted(tot.items(),key=lambda x:-x[1]): print(f"  {s:<14} {n}",flush=True)
    else:
        lim=int(sys.argv[3]) if len(sys.argv)>3 else None
        process(site,arg,cats,lim)
