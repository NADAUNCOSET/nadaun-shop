# -*- coding: utf-8 -*-
"""Cafe24 범용 스크래퍼 — 소스 11곳 공용 템플릿 (2026-07-09, sources.md 참조).
   리스트(/product/list.html?cate_no=N&page=P) → 상세(product_no) → 정가 캡처 → webp → R2 → 브랜드별 JSON.
   stable id = <source>-<product_no>. 이미 R2에 있으면 skip(증분). 정가 우선(소비자가>판매가) 룰.
   카테고리는 소스 원문(cat_path)으로 보존 → 최종 분류는 kpp_classify.py (KPP 택소노미 SoT).

   실행:
     python cafe24.py <site> NAV               # 카테고리 트리 덤프(확인용)
     python cafe24.py <site> <cate_no> [LIMIT] # 한 카테고리 파일럿
     python cafe24.py <site> ALL [LIMIT]       # 전 카테고리 (체크포인트 data/_<site>_done.json)
   site = fomex | benro | hktools | sama | hipixel | mustcolor | motionnine | onnoff | ldnet | cinemall | bando
"""
import sys, io, re, json, time, socket
from pathlib import Path
socket.setdefaulttimeout(60)   # 행 방지 (kpp 2026-07-08 타르핏 사고와 동일 대응)
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
 "fomex":      {"base":"https://fomex.co.kr",        "name":"포멕스"},
 "benro":      {"base":"https://benrokorea.co.kr",   "name":"벤로코리아"},
 "hktools":    {"base":"https://hktools.co.kr",      "name":"HK툴스"},
 "sama":       {"base":"https://samastore.co.kr",    "name":"삼아스토어"},
 "hipixel":    {"base":"https://hipixelplus.co.kr",  "name":"하이픽셀플러스"},
 "mustcolor":  {"base":"https://mustcolor.com",      "name":"머스트컬러"},
 "motionnine": {"base":"https://motionnine.com",     "name":"모션나인"},
 "onnoff":     {"base":"https://onnoff.kr",          "name":"온앤오프미디어"},
 "ldnet":      {"base":"https://ldnet.co.kr",        "name":"엘디네트웍스"},
 "cinemall":   {"base":"https://cinemall.co.kr",     "name":"시네몰"},
 "bando":      {"base":"https://bandocamera.co.kr",  "name":"반도카메라"},
}

UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36"}
S = requests.Session(); S.headers.update(UA)

import threading
def _fetch_one(u,out):
    try: out.append(S.get(u,timeout=30))
    except Exception as e: out.append(e)

def get(u, retries=3, deadline=50):
    """절대 데드라인 get — 타르핏 드립피드 대응 + chardet은 텍스트 응답만 (scraper-hang-deadline-patterns 2026-07-09)."""
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
    if u.startswith("//"): return "https:"+u
    if u.startswith("/"): return base+u
    if u.startswith("http"): return u
    return base+"/"+u.lstrip("./")

# ── 카테고리 네비 ───────────────────────────────────────────────
def fetch_nav(base):
    """홈에서 cate_no 링크 전부 수집 → {cate_no: name}."""
    soup=BeautifulSoup(get(base+"/").text,"html.parser")
    cats={}
    for a in soup.select('a[href*="cate_no="]'):
        m=re.search(r"cate_no=(\d+)",a.get("href",""))
        if not m: continue
        cid=m.group(1); nm=clean(a.get_text())
        if nm and (cid not in cats or len(cats[cid])<2):
            cats[cid]=nm
    return cats

# ── 리스트 ─────────────────────────────────────────────────────
LIST_SEL = "ul.prdList > li, li[id*='anchorBox'], .xans-product-listnormal > ul > li, .prdList__item"
def list_items(base, cate_no, max_pages=100):
    seen={}
    for page in range(1,max_pages+1):
        soup=BeautifulSoup(get(f"{base}/product/list.html?cate_no={cate_no}&page={page}").text,"html.parser")
        got=0
        for li in soup.select(LIST_SEL):
            a=li.select_one("a[href*='/product/']")
            if not a: continue
            href=a.get("href","")
            m=re.search(r"/product/[^/]+/(\d+)",href) or re.search(r"product_no=(\d+)",href)
            if not m: continue
            sid=m.group(1)
            if sid in seen: continue
            seen[sid]=absu(base,href); got+=1
        if got==0: break
        if page%10==0: print(f"  … 리스트 수집 p{page} ({len(seen)}개)",flush=True)
        time.sleep(0.4)
    return seen   # {product_no: url}

# ── 상세 ───────────────────────────────────────────────────────
def parse_item(base, url):
    soup=BeautifulSoup(get(url).text,"html.parser")
    # og:title이 2개인 사이트(cinemall: 첫번째=슬로건, 마지막=상품명) → 마지막 것 사용
    ogs=[m.get("content","") for m in soup.select('meta[property="og:title"]') if m.get("content")]
    name=clean(ogs[-1]) if ogs else clean(soup.title.get_text() if soup.title else "")
    name=re.sub(r"\s*-\s*시네몰\s*$","",name)   # cinemall 상점명 접미 제거
    name=re.sub(r"\s*[|\-]\s*[^|\-]*$","",name) if len(name)>60 else name
    # 정가(소비자가) 우선, 없으면 판매가 (룰: taxonomy_kpp.md "가격=정가")
    listp=0
    for sel in ("#span_product_price_custom", ".xans-product-detail .custom", "#pricett del", ".consumer"):
        el=soup.select_one(sel)
        if el and price_num(el.get_text()): listp=price_num(el.get_text()); break
    salep=0
    for sel in ("#span_product_price_text", ".xans-product-detail .price", "#span_product_price_sale"):
        el=soup.select_one(sel)
        if el and price_num(el.get_text()): salep=price_num(el.get_text()); break
    if not (listp or salep):   # 폴백: og/meta 가격
        mp=soup.select_one('meta[property="product:price:amount"], meta[property="og:price:amount"]')
        if mp: salep=price_num(mp.get("content"))
    price=listp or salep
    # 이미지
    def src(i): return absu(base, i.get("src") or i.get("ec-data-src") or i.get("data-src") or "")
    main=[]
    ogimg=soup.select_one('meta[property="og:image"]')
    if ogimg and ogimg.get("content"): main.append(absu(base,ogimg.get("content")))
    main+=[src(i) for i in soup.select(".keyImg img, .xans-product-image img, .bigImage img")]
    main+=[re.sub(r"/(small|tiny|medium)/","/big/",src(i)) for i in soup.select(".listImg img, .xans-product-addimage img, .thumbnail li img, .xans-product-addimage-1 img")]
    det=[src(i) for i in soup.select("#prdDetail img, .cont img, .xans-product-detail img, #detail img")]
    det=[d for d in det if d and not re.search(r"(banner|notice|delivery|benefit|event|as_guide|_cate|guide_)",d.lower())]
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
        r=get(src); ct=r.headers.get("Content-Type","")
        if "image" not in ct or len(r.content)<900: return ""
        return r2_put(key,to_webp(r.content,maxw))
    except Exception: return ""

# ── 처리 ───────────────────────────────────────────────────────
def process(site, cate_no, cats, limit=None, done_ids=None):
    global S
    S=requests.Session(); S.headers.update(UA)   # 카테고리마다 새 세션 (타르핏/쿠키 방지)
    base=SITES[site]["base"]; cname=cats.get(cate_no,cate_no)
    items=list_items(base,cate_no)
    if done_ids is not None:   # ALL 모드: 다른 카테고리에서 이미 처리한 상품 스킵(중복노출 다수)
        items={sid:u for sid,u in items.items() if sid not in done_ids}
    ids=list(items)[:limit] if limit else list(items)
    print(f"[{SITES[site]['name']}/{cname} · cate_no={cate_no}] 상품 {len(ids)}개")
    by_brand={}
    for i,sid in enumerate(ids,1):
        try: d=parse_item(base,items[sid])
        except Exception as e: print(f"  ! {sid} 파싱실패 {e}"); continue
        ko,slug=brand_of(d["name"]); pid=f"{site}-{sid}"
        rec={"id":pid,"source":site,"source_id":sid,"name":d["name"],
             "brand":ko,"brand_slug":slug,"category":cname,"cat_path":[cname],
             "cate_no":cate_no,"price":d["price"],"list_price":d["list_price"],
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
        print("사용법: python cafe24.py <site> NAV|ALL|<cate_no> [LIMIT]"); print("site =", " | ".join(SITES)); sys.exit(1)
    site=sys.argv[1]; arg=sys.argv[2]; base=SITES[site]["base"]
    cats=fetch_nav(base)
    if arg=="NAV":
        print(f"[{SITES[site]['name']}] 카테고리 {len(cats)}개")
        for c,n in sorted(cats.items()): print(f"  {c:<8} {n}")
    elif arg=="ALL":
        lim=int(sys.argv[3]) if len(sys.argv)>3 else None
        ckpt=DATA.parent/f"_{site}_done.json"
        st=json.load(open(ckpt,encoding="utf-8")) if ckpt.exists() else {"cats":[],"ids":[]}
        if isinstance(st,list): st={"cats":st,"ids":[]}
        done_set=set(st["cats"]); done_ids=set(st["ids"])
        SKIP_CAT=("개인결제","상품명")
        todo=[c for c in sorted(cats) if not any(s in cats[c] for s in SKIP_CAT)]; tot={}
        print(f"=== {SITES[site]['name']} 전체 스크랩: 카테고리 {len(todo)}개 (완료스킵 {len(done_set)}, 상품스킵 {len(done_ids)}) ===",flush=True)
        for k,c in enumerate(todo,1):
            if c in done_set: continue
            try:
                bb=process(site,c,cats,lim,done_ids)
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
