# -*- coding: utf-8 -*-
"""세기몰(saeki.co.kr) 스크래퍼 — 자체 엔진, JSON 리스트 API (2026-07-17, sources.md 자체몰 정찰).
   카테고리(/category/main?dspCateId=N, 홈에서 수집) → CSRF 메타 파싱 → POST /category/search-cate-item-list-json
   → 아이템 JSON(itemNm·brndNm·spprc정가·slprc판매가·썸네일경로) → 상세(/item/itemDetail?itemId=PD..)에서 설명이미지
   → webp → R2 → 브랜드별 JSON. stable id = saeki-<itemId>. 이미지 CDN = https://cdn.saeki.co.kr/malluploadfile<path>.
   카테고리명 = 아이템 JSON의 dspCateSclNm(소분류) 원문 보존 → kpp_classify.

   실행: python saeki.py NAV | python saeki.py <dspCateId> [LIMIT] | python saeki.py ALL [LIMIT]
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

BASE="https://www.saeki.co.kr"
CDN="https://cdn.saeki.co.kr/malluploadfile"
SITE="saeki"; SITE_NAME="세기몰"

UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36"}
S = requests.Session(); S.headers.update(UA)

import threading
def _run_bounded(fn, deadline, *a, **kw):
    out=[]
    def run():
        try: out.append(fn(*a,**kw))
        except Exception as e: out.append(e)
    t=threading.Thread(target=run,daemon=True); t.start(); t.join(deadline)
    if out and not isinstance(out[0],Exception): return out[0]
    raise RuntimeError("op 데드라인/실패")
def get(u, retries=3, deadline=50):
    global S
    for k in range(retries):
        try: return _run_bounded(S.get,deadline,u,timeout=30)
        except Exception:
            S=requests.Session(); S.headers.update(UA)
            if k==retries-1: raise
            time.sleep(2*(k+1))
def post(u, data, headers=None, retries=3, deadline=50):
    for k in range(retries):
        try: return _run_bounded(S.post,deadline,u,data=data,headers=headers or {},timeout=30)
        except Exception:
            if k==retries-1: raise
            time.sleep(2*(k+1))
def clean(t): return re.sub(r"\s+"," ",(t or "").strip())

def to_webp(b, maxw, q=82):
    im=Image.open(io.BytesIO(b)).convert("RGB")
    if im.width>maxw: im=im.resize((maxw,int(im.height*maxw/im.width)),Image.LANCZOS)
    o=io.BytesIO(); im.save(o,"WEBP",quality=q,method=6); return o.getvalue()
def r2_exists(key):
    try: _run_bounded(S3.head_object,20,Bucket=BUCKET,Key=key); return True
    except Exception: return False
def r2_put(key,data):
    _run_bounded(S3.put_object,60,Bucket=BUCKET,Key=key,Body=data,ContentType="image/webp",
                 CacheControl="public,max-age=31536000,immutable")
    return f"{PUBLIC}/{key}"
def upl(src,key,maxw):
    if not src or src.startswith("data:"): return ""
    if r2_exists(key): return f"{PUBLIC}/{key}"
    try:
        r=get(src)
        if len(r.content)<900 or b"<html" in r.content[:400].lower(): return ""
        data=_run_bounded(to_webp,120,r.content,maxw)   # PIL 폭탄 이미지 방어
        return r2_put(key,data)
    except Exception: return ""

def cdnu(p):
    if not p: return ""
    if p.startswith("http"): return p
    return CDN+p

# ── 카테고리 ────────────────────────────────────────────────────
def fetch_nav():
    """카테고리 SoT = data/_saeki_categories.json (GNB가 JS렌더라 브라우저 DOM에서 덤프, 2026-07-17).
       폴백: 홈 HTML의 dspCateId 링크(기획전 몇 개뿐)."""
    fp=DATA.parent/"_saeki_categories.json"
    if fp.exists():
        return json.load(open(fp,encoding="utf-8"))
    r=get(BASE+"/main"); r.encoding=r.apparent_encoding
    cats={}
    for m in re.finditer(r"dspCateId=(\d+)",r.text): cats.setdefault(m.group(1),m.group(1))
    return cats

# ── 리스트 (JSON API + CSRF) ───────────────────────────────────
def list_items(cate_id, max_pages=100):
    """카테고리 페이지에서 CSRF 취득 → JSON API 페이지네이션. 반환 {itemId: item_json}."""
    r=get(f"{BASE}/category/main?dspCateId={cate_id}"); r.encoding=r.apparent_encoding
    soup=BeautifulSoup(r.text,"html.parser")
    tok=soup.select_one('meta[name="X-CSRF-TOKEN"], meta[name="CSRF-TOKEN"], meta[name="_csrf"]')
    token=tok.get("content") if tok else ""
    # 페이지 hidden 필드에서 검색 파라미터 보충 (dspCateLclId·Depth 등)
    hid={i.get("name"):i.get("value","") for i in soup.select("input[type=hidden]") if i.get("name")}
    seen={}
    for page in range(1,max_pages+1):
        form={"pageName":"categoryMain","pageNo":str(page),"saleItem":"","packageItem":"",
              "noSoldOutItem":"","sorting":"favor","rowsPerPage":"40",
              "dspCateId":cate_id,"brndId":"","dspCateDepth":hid.get("dspCateDepth",""),
              "color":"","stPrice":"","edPrice":"","addFilter":"","brndIdList":"",
              "dspCateIdList":cate_id,"dspCateLclId":hid.get("dspCateLclId",""),"_format":"json","_csrf":token}
        rr=post(f"{BASE}/category/search-cate-item-list-json",form,
                headers={"X-CSRF-TOKEN":token,"X-Requested-With":"XMLHttpRequest",
                         "Referer":f"{BASE}/category/main?dspCateId={cate_id}"})
        try: d=rr.json()
        except Exception:
            print(f"  ! JSON 파싱실패 p{page} (HTTP {rr.status_code})"); break
        items=d.get("itemList") or []
        got=0
        for it in items:
            iid=it.get("itemId")
            if iid and iid not in seen: seen[iid]=it; got+=1
        pg=d.get("paginationInfo") or {}
        if got==0 or page>=int(pg.get("totalPageCount") or 1): break
        time.sleep(0.4)
    return seen

# ── 상세 (설명이미지) ───────────────────────────────────────────
def detail_images(item_id):
    try:
        r=get(f"{BASE}/item/itemDetail?itemId={item_id}"); r.encoding=r.apparent_encoding
        soup=BeautifulSoup(r.text,"html.parser")
        det=[]
        for i in soup.find_all("img"):
            u=i.get("src") or i.get("data-src") or ""
            if "/public/images/item/" in u: det.append(cdnu(u))
        det=[d for d in det if not re.search(r"(banner|notice|delivery|benefit|event)",d.lower())]
        s=[];[s.append(x) for x in det if x not in s];return s
    except Exception: return []

# ── 처리 ───────────────────────────────────────────────────────
def process(cate_id, cats, limit=None, done_ids=None):
    global S
    S=requests.Session(); S.headers.update(UA)
    items=list_items(cate_id)
    if done_ids is not None:
        items={k:v for k,v in items.items() if k not in done_ids}
    ids=list(items)[:limit] if limit else list(items)
    cname=cats.get(cate_id,cate_id)
    print(f"[{SITE_NAME}/{cname} · dspCateId={cate_id}] 상품 {len(ids)}개")
    by_brand={}
    for i,iid in enumerate(ids,1):
        it=items[iid]
        name=clean(it.get("itemNm")); brnd=clean(it.get("brndNm") or "")
        listp=int(it.get("spprc") or 0); salep=int(it.get("slprc") or 0)
        if listp==salep: listp=0
        price=listp or salep
        inquiry=(it.get("prcInqYn")=="Y") or price==0
        cat=clean(it.get("dspCateSclNm") or it.get("dspCateMclNm") or cname)
        ko,slug=brand_of(f"{brnd} {name}".strip())
        pid=f"{SITE}-{iid}"
        main=[cdnu(it.get("itemPcAtchFilePath") or it.get("itemAtchFilePath") or "")]
        main=[m for m in main if m]
        det=detail_images(iid)
        rec={"id":pid,"source":SITE,"source_id":iid,"name":name,
             "brand":ko,"brand_slug":slug,"category":cat,"cat_path":[cat],
             "cate_no":cate_id,"price":price,"list_price":listp,"sale_price":salep,
             "inquiry":inquiry,"source_url":f"{BASE}/item/itemDetail?itemId={iid}",
             "images":{"thumb":"","main":[],"detail":[]}}
        if main: rec["images"]["thumb"]=upl(main[0],f"shop/thumbnails/{slug}/{pid}.webp",600)
        for n,src in enumerate(main,1):
            u=upl(src,f"shop/images/{slug}/{pid}/main_{n}.webp",1600)
            if u: rec["images"]["main"].append(u)
        for n,src in enumerate(det,1):
            u=upl(src,f"shop/detail/{slug}/{pid}/{n:02d}.webp",1400)
            if u: rec["images"]["detail"].append(u)
            if n%5==0: print(f"    … 이미지 {n}/{len(det)}",flush=True)
        by_brand.setdefault(slug,{"brand":ko,"brand_slug":slug,"products":{}})
        by_brand[slug]["products"][pid]=rec
        if done_ids is not None: done_ids.add(iid)
        flag="📞" if inquiry else ""
        print(f"  {i}/{len(ids)} [{ko}] {name[:32]:<32} {price:>9,}{flag}  m{len(rec['images']['main'])} d{len(rec['images']['detail'])}")
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
    if len(sys.argv)<2:
        print("사용법: python saeki.py NAV | <dspCateId> [LIMIT] | ALL [LIMIT]"); sys.exit(1)
    arg=sys.argv[1]
    cats=fetch_nav()
    if arg=="NAV":
        print(f"[{SITE_NAME}] 카테고리 {len(cats)}개")
        for c,n in sorted(cats.items()): print(f"  {c:<8} {n}")
    elif arg=="ALL":
        lim=int(sys.argv[2]) if len(sys.argv)>2 else None
        ckpt=DATA.parent/f"_{SITE}_done.json"
        st=json.load(open(ckpt,encoding="utf-8")) if ckpt.exists() else {"cats":[],"ids":[]}
        done_set=set(st["cats"]); done_ids=set(st["ids"])
        SKIP_CAT=("개인결제","상품명","고객결제")
        todo=[c for c in sorted(cats) if not any(s in cats[c] for s in SKIP_CAT)]; tot={}
        print(f"=== {SITE_NAME} 전체 스크랩: 카테고리 {len(todo)}개 (완료스킵 {len(done_set)}, 상품스킵 {len(done_ids)}) ===",flush=True)
        for k,c in enumerate(todo,1):
            if c in done_set: continue
            try:
                bb=process(c,cats,lim,done_ids)
                for s in bb: tot[s]=tot.get(s,0)+len(bb[s]["products"])
                done_set.add(c)
                json.dump({"cats":sorted(done_set),"ids":sorted(done_ids)},open(ckpt,"w",encoding="utf-8"))
            except Exception as e:
                print(f"  !! 카테고리 {c} 실패(스킵): {e}",flush=True)
            print(f"--- 진행 {k}/{len(todo)}, 누계 {sum(tot.values())} ---",flush=True)
        print("\n=== 완료 브랜드별 누계 ===",flush=True)
        for s,n in sorted(tot.items(),key=lambda x:-x[1]): print(f"  {s:<14} {n}",flush=True)
    else:
        lim=int(sys.argv[2]) if len(sys.argv)>2 else None
        process(arg,cats,lim)
