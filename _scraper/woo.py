# -*- coding: utf-8 -*-
"""WooCommerce Store API 스크래퍼 — 토브테크 tovmall.co.kr (2026-07-17, sources.md 자체몰 정찰).
   공개 Store API(/wp-json/wc/store/v1/products?per_page=100&page=P) 전체 덤프 → webp → R2 → 브랜드별 JSON.
   stable id = tov-<wp id>. 가격: sale=prices.price, 정가=prices.regular_price (KRW minor unit 0).
   상세이미지 = description HTML 내 <img>. 카테고리 = categories[].name 원문 보존 → kpp_classify.

   실행: python woo.py tov ALL [LIMIT] | python woo.py tov PAGE <n>
"""
import sys, io, re, json, time, socket, html as htmlmod
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

SITES = {"tov": {"base":"https://tovmall.co.kr", "name":"토브테크"}}

UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36"}
S = requests.Session(); S.headers.update(UA)

import threading
def _fetch_one(u,out):
    try: out.append(S.get(u,timeout=30))
    except Exception as e: out.append(e)
def get(u, retries=3, deadline=50):
    global S
    for k in range(retries):
        out=[]
        t=threading.Thread(target=_fetch_one,args=(u,out),daemon=True)
        t.start(); t.join(deadline)
        if out and not isinstance(out[0],Exception): return out[0]
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
        r=get(src)
        if len(r.content)<900 or b"<html" in r.content[:400].lower(): return ""
        data=_bounded(to_webp,120,r.content,maxw)   # PIL 폭탄 이미지 방어
        return r2_put(key,data)
    except Exception: return ""

def save(by_brand):
    for slug,pack in by_brand.items():
        fp=DATA/f"{slug}.json"
        if fp.exists():
            old=json.load(open(fp,encoding="utf-8"))
            old.setdefault("products",{}).update(pack["products"])
            old["brand"]=pack["brand"]; old["brand_slug"]=slug; pack=old
        json.dump(pack,open(fp,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
        print(f"  → data/products/{slug}.json ({len(pack['products'])}개)")

def process_page(site, page, limit=None, done_ids=None):
    base=SITES[site]["base"]
    r=get(f"{base}/wp-json/wc/store/v1/products?per_page=100&page={page}")
    prods=r.json()
    if not prods: return None
    if done_ids is not None:
        prods=[p for p in prods if str(p["id"]) not in done_ids]
    if limit: prods=prods[:limit]
    print(f"[토브테크 p{page}] 상품 {len(prods)}개")
    by_brand={}
    for i,p in enumerate(prods,1):
        sid=str(p["id"])
        name=clean(htmlmod.unescape(p.get("name") or ""))
        if not name:   # 이름 없는 유령 상품(중고 등) skip
            if done_ids is not None: done_ids.add(sid)
            continue
        pr=p.get("prices") or {}
        salep=int(pr.get("price") or 0); listp=int(pr.get("regular_price") or 0)
        if listp==salep: listp=0
        price=listp or salep
        cname=" / ".join(c["name"] for c in (p.get("categories") or [])[:2]) or "미분류"
        main=[im.get("src") for im in (p.get("images") or []) if im.get("src")]
        desc=(p.get("description") or "")+(p.get("short_description") or "")
        det=[m.group(1) for m in re.finditer(r'<img[^>]+src="([^"]+)"',desc)]
        det=[d for d in det if not re.search(r"(banner|notice|delivery|benefit|event)",d.lower())]
        ko,slug=brand_of(name); pid=f"{site}-{sid}"
        rec={"id":pid,"source":site,"source_id":sid,"name":name,
             "brand":ko,"brand_slug":slug,"category":cname,"cat_path":[cname],
             "cate_no":"","price":price,"list_price":listp,"sale_price":salep,
             "inquiry":price==0,"source_url":p.get("permalink") or "",
             "images":{"thumb":"","main":[],"detail":[]}}
        if main: rec["images"]["thumb"]=upl(main[0],f"shop/thumbnails/{slug}/{pid}.webp",600)
        for n,src in enumerate(main[:10],1):
            u=upl(src,f"shop/images/{slug}/{pid}/main_{n}.webp",1600)
            if u: rec["images"]["main"].append(u)
        for n,src in enumerate(det,1):
            u=upl(src,f"shop/detail/{slug}/{pid}/{n:02d}.webp",1400)
            if u: rec["images"]["detail"].append(u)
        by_brand.setdefault(slug,{"brand":ko,"brand_slug":slug,"products":{}})
        by_brand[slug]["products"][pid]=rec
        if done_ids is not None: done_ids.add(sid)
        flag="📞" if price==0 else ""
        print(f"  {i}/{len(prods)} [{ko}] {name[:32]:<32} {price:>9,}{flag}  m{len(rec['images']['main'])} d{len(rec['images']['detail'])}")
        time.sleep(0.2)
    save(by_brand)
    return by_brand

if __name__=="__main__":
    if len(sys.argv)<3 or sys.argv[1] not in SITES:
        print("사용법: python woo.py tov ALL [LIMIT] | python woo.py tov PAGE <n>"); sys.exit(1)
    site=sys.argv[1]; arg=sys.argv[2]
    if arg=="PAGE":
        process_page(site,int(sys.argv[3]),limit=5)
    elif arg=="ALL":
        lim=int(sys.argv[3]) if len(sys.argv)>3 else None
        ckpt=DATA.parent/f"_{site}_done.json"
        st=json.load(open(ckpt,encoding="utf-8")) if ckpt.exists() else {"pages":[],"ids":[]}
        done_pages=set(st.get("pages",[])); done_ids=set(st["ids"])
        r=get(f"{SITES[site]['base']}/wp-json/wc/store/v1/products?per_page=100&page=1")
        totpg=int(r.headers.get("X-WP-TotalPages") or 1)
        print(f"=== 토브테크 전체 스크랩: {r.headers.get('X-WP-Total')}개 / {totpg}페이지 (완료스킵 {len(done_pages)}p, 상품스킵 {len(done_ids)}) ===",flush=True)
        tot={}
        for pg in range(1,totpg+1):
            if pg in done_pages: continue
            try:
                bb=process_page(site,pg,lim,done_ids)
                if bb is None: break
                for s in bb: tot[s]=tot.get(s,0)+len(bb[s]["products"])
                done_pages.add(pg)
                json.dump({"pages":sorted(done_pages),"ids":sorted(done_ids)},open(ckpt,"w",encoding="utf-8"))
            except Exception as e:
                print(f"  !! 페이지 {pg} 실패(스킵): {e}",flush=True)
            print(f"--- 진행 {pg}/{totpg}, 누계 {sum(tot.values())} ---",flush=True)
        print("\n=== 완료 브랜드별 누계 ===",flush=True)
        for s,n in sorted(tot.items(),key=lambda x:-x[1]): print(f"  {s:<14} {n}",flush=True)
