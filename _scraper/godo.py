# -*- coding: utf-8 -*-
"""godo(NHN커머스) 범용 스크래퍼 — 소스 3곳 공용 템플릿 (2026-07-17, sources.md 참조. cafe24.py 패턴).
   리스트(/goods/goods_list.php?cateCd=C&page=P) → 상세(goods_view.php?goodsNo=N) → 정가 캡처 → webp → R2 → 브랜드별 JSON.
   stable id = <source>-<goodsNo>. 이미 R2에 있으면 skip(증분). 정가 우선(정가/소비자가>판매가) 룰.
   카테고리는 소스 원문(cat_path)으로 보존 → 최종 분류는 kpp_classify.py (KPP 택소노미 SoT).

   실행:
     python godo.py <site> NAV               # 카테고리 트리 덤프(확인용)
     python godo.py <site> <cateCd> [LIMIT]  # 한 카테고리 파일럿
     python godo.py <site> ALL [LIMIT]       # 전 카테고리 (체크포인트 data/_<site>_done.json)
   site = redsun | calla | lmount
"""
import sys, io, re, json, time, socket
from pathlib import Path
socket.setdefaulttimeout(60)   # 행 방지 (kpp 2026-07-08 타르핏 사고와 동일 대응)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import requests
from bs4 import BeautifulSoup
from PIL import Image
from brands_map import brand_of

sys.path.insert(0, r"\\Nadaunproject\nadaunproject\_claude\jellyfin_proxy\_r2")   # 허브 이동 후 새 경로 (2026-07-17)
from _r2_common import client, BUCKET
S3 = client()
PUBLIC = "https://media.nadaun.co"
ROOT = Path(r"\\Nadaunproject\nadaunproject\_Site\nadaun-shop")
DATA = ROOT/"data"/"products"; DATA.mkdir(parents=True, exist_ok=True)

SITES = {
 "redsun": {"base":"https://redsun.co.kr",   "name":"디지털홍일"},
 "calla":  {"base":"https://callamedia.kr",  "name":"칼라미디어"},
 "lmount": {"base":"https://l-mount.co.kr",  "name":"엘디엘마운트"},
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
    """홈+리스트 사이드바에서 cateCd 링크 수집 → {cateCd: name}. godo는 계층코드(001/001002/…).
       calla처럼 홈 메뉴가 이미지(텍스트 없음)면 리스트 페이지 사이드바에서 이름 보충+하위 발견 (2026-07-17)."""
    cats={}
    def harvest(soup):
        for a in soup.select('a[href*="cateCd="]'):
            m=re.search(r"cateCd=(\d+)",a.get("href",""))
            if not m: continue
            cid=m.group(1)
            nm=clean(a.get_text()).lstrip("▷►▶·• ").strip()
            if re.fullmatch(r"\d+|[\W_]*",nm or ""): nm=""   # 페이지네이션 숫자/기호 링크 제외
            if cid not in cats: cats[cid]=nm
            elif nm and len(cats[cid])<2: cats[cid]=nm
    harvest(BeautifulSoup(get(base+"/").text,"html.parser"))
    for _ in range(2):   # pass1: 이름보충+하위발견, pass2: 새로 발견된 것 보충
        unnamed=[c for c,n in cats.items() if not n]
        if not unnamed: break
        for c in unnamed:
            try: harvest(BeautifulSoup(get(f"{base}/goods/goods_list.php?cateCd={c}").text,"html.parser"))
            except Exception: pass
            time.sleep(0.3)
    for c in cats:
        if not cats[c]: cats[c]=c   # 끝내 이름 없으면 코드 그대로
    return cats

# ── 리스트 ─────────────────────────────────────────────────────
def list_items(base, cate_cd, max_pages=100):
    seen={}
    for page in range(1,max_pages+1):
        soup=BeautifulSoup(get(f"{base}/goods/goods_list.php?cateCd={cate_cd}&page={page}").text,"html.parser")
        got=0
        for a in soup.select('a[href*="goods_view.php"]'):
            m=re.search(r"goodsNo=(\d+)",a.get("href",""))
            if not m: continue
            sid=m.group(1)
            if sid in seen: continue
            seen[sid]=f"{base}/goods/goods_view.php?goodsNo={sid}"; got+=1
        if got==0: break
        if page%10==0: print(f"  … 리스트 수집 p{page} ({len(seen)}개)",flush=True)
        time.sleep(0.4)
    return seen   # {goodsNo: url}

# ── 상세 ───────────────────────────────────────────────────────
def parse_item(base, url):
    gn=re.search(r"goodsNo=(\d+)",url).group(1)
    soup=BeautifulSoup(get(url).text,"html.parser")
    # 상품명: item_detail_tit h3 우선 (calla는 og:title=사이트명), 폴백 og:title
    h3=soup.select_one(".item_detail_tit h3, .item_detail_tit h2")
    og=soup.select_one('meta[property="og:title"]')
    name=clean(h3.get_text()) if h3 and len(clean(h3.get_text()))>3 else ""
    if not name:
        name=clean(og.get("content")) if og and og.get("content") else clean(soup.title.get_text() if soup.title else "")
    name=re.sub(r"^\[[^\]]*\]\s*","",name) if name.startswith("[") and "]" in name[:25] and len(name)>30 else name
    # 정가(정가/소비자가) 우선, 없으면 판매가 — godo는 li.price/dl 안 <strong>라벨</strong><div>값</div>
    listp=salep=0
    for row in soup.select("li, dl, tr"):
        lab=row.find(["strong","dt","th"])
        if not lab: continue
        lt=clean(lab.get_text())
        val=price_num(row.get_text().replace(lt,"",1))
        if not val: continue
        if lt in ("정가","소비자가") and not listp: listp=val
        elif lt=="판매가" and not salep: salep=val
    if not (listp or salep):
        mp=soup.select_one('meta[property="product:price:amount"], meta[property="product:sale_price:amount"]')
        if mp: salep=price_num(mp.get("content"))
    price=listp or salep
    # 이미지: 메인 = 자기 goodsNo 경로만 (관련상품 위젯 오염 방지), /thumb/ 제외
    def src(i): return absu(base, i.get("src") or i.get("data-src") or "")
    main=[]
    ogimg=soup.select_one('meta[property="og:image"]')
    if ogimg and ogimg.get("content"): main.append(absu(base,ogimg.get("content")))
    for i in soup.find_all("img"):
        u=src(i)
        if u and f"/goods/{gn}/" in u and "/thumb/" not in u: main.append(u)
    # 상세설명: #detail 영역 + 에디터 업로드(data/editor/goods) 이미지
    det=[]
    box=soup.select_one("#detail, .detail_cont, .goods_description, #div_goods_memo")
    if box:   # 박스 안이면 에디터 업로드 전부 (redsun은 data/editor/<제품명>/ 경로도 씀)
        det=[src(i) for i in box.find_all("img") if src(i)]
    else:
        for i in soup.find_all("img"):
            u=src(i)
            if u and ("data/editor/" in u or (f"/goods/{gn}/image/" in u and "/thumb/" not in u)): det.append(u)
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
        r=get(src)   # godomall CDN이 이미지에 multipart/form-data CT를 주는 케이스 → CT 대신 디코딩으로 판정
        if len(r.content)<900 or b"<html" in r.content[:400].lower(): return ""
        return r2_put(key,to_webp(r.content,maxw))
    except Exception: return ""

# ── 처리 ───────────────────────────────────────────────────────
def process(site, cate_cd, cats, limit=None, done_ids=None):
    global S
    S=requests.Session(); S.headers.update(UA)   # 카테고리마다 새 세션 (타르핏/쿠키 방지)
    base=SITES[site]["base"]; cname=cats.get(cate_cd,cate_cd)
    items=list_items(base,cate_cd)
    if done_ids is not None:   # ALL 모드: 다른 카테고리에서 이미 처리한 상품 스킵(계층 카테고리 중복노출 다수)
        items={sid:u for sid,u in items.items() if sid not in done_ids}
    ids=list(items)[:limit] if limit else list(items)
    print(f"[{SITES[site]['name']}/{cname} · cateCd={cate_cd}] 상품 {len(ids)}개")
    by_brand={}
    for i,sid in enumerate(ids,1):
        try: d=parse_item(base,items[sid])
        except Exception as e: print(f"  ! {sid} 파싱실패 {e}"); continue
        ko,slug=brand_of(d["name"]); pid=f"{site}-{sid}"
        rec={"id":pid,"source":site,"source_id":sid,"name":d["name"],
             "brand":ko,"brand_slug":slug,"category":cname,"cat_path":[cname],
             "cate_no":cate_cd,"price":d["price"],"list_price":d["list_price"],
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
        print("사용법: python godo.py <site> NAV|ALL|<cateCd> [LIMIT]"); print("site =", " | ".join(SITES)); sys.exit(1)
    site=sys.argv[1]; arg=sys.argv[2]; base=SITES[site]["base"]
    cats=fetch_nav(base)
    if arg=="NAV":
        print(f"[{SITES[site]['name']}] 카테고리 {len(cats)}개")
        for c,n in sorted(cats.items()): print(f"  {c:<10} {n}")
    elif arg=="ALL":
        lim=int(sys.argv[3]) if len(sys.argv)>3 else None
        ckpt=DATA.parent/f"_{site}_done.json"
        st=json.load(open(ckpt,encoding="utf-8")) if ckpt.exists() else {"cats":[],"ids":[]}
        if isinstance(st,list): st={"cats":st,"ids":[]}
        done_set=set(st["cats"]); done_ids=set(st["ids"])
        SKIP_CAT=("개인결제","상품명","고객결제")
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
