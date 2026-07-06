# -*- coding: utf-8 -*-
"""clmedia(Cafe24) → 나다운샵 제품DB 파이프라인.
   리스트(이름/가격/썸네일) + 상세(대표/상세이미지) → webp 최적화 → R2 업로드 → 브랜드별 JSON.
   stable id = clmedia-<상품번호>. 이미 R2에 있으면 skip(증분). 수만개 대비.
   실행: python clmedia.py <cate_no> [LIMIT]"""
import sys, io, re, json, time, os
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import requests
from bs4 import BeautifulSoup
from PIL import Image

# R2 (jellyfin _r2_common 재사용)
sys.path.insert(0, r"\\Nadaunproject\nadaunproject\_DAVINCI NADAUN PROJECT\_claude\jellyfin_proxy\_r2")
from _r2_common import client, BUCKET
S3 = client()
PUBLIC = "https://media.nadaun.co"

ROOT = Path(r"\\Nadaunproject\nadaunproject\_DAVINCI NADAUN PROJECT\_Site\nadaun-shop")
DATA = ROOT/"data"/"products"; DATA.mkdir(parents=True, exist_ok=True)

BASE = "https://www.clmedia.co.kr"
S = requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0 Chrome/149 Safari/537.36"})

# 브랜드 한글→슬러그 (상품명 앞부분 매칭). 미매칭 → _기타
BRANDS = [
 ("틸타","tilta"),("어퓨처","aputure"),("아마란","aputure"),("스몰리그","smallrig"),("아리","arri"),
 ("홀리랜드","hollyland"),("난라이트","nanlite"),("난룩스","nanlux"),("프로포토","profoto"),
 ("소니","sony"),("캐논","canon"),("후지","fujifilm"),("디제이아이","dji"),("DJI","dji"),
 ("라오와","laowa"),("젠하이저","sennheiser"),("슈어","shure"),("니시","nisi"),("NISI","nisi"),
 ("쿠포","kupo"),("젠트리","gentree"),("이지리그","easyrig"),("맨프로토","manfrotto"),
 ("삭틀러","sachtler"),("자이스","zeiss"),("조프","dzofilm"),("디죠","dzofilm"),("블랙매직","blackmagic"),
 ("호크우드","hawkwood"),("모션9","motion9"),("노바칩스","novachips"),("기트조","gitzo"),("레오포토","leofoto"),
 ("어퓨쳐","aputure"),("퀄라이트","qualite"),("오스람","osram"),("잭커리","jackery"),("아스테라","astera"),
 ("에프엑스리온","fxlion"),("나이트코어","nitecore"),("아트뮤","artmu"),("ZGCINE","zgcine"),("ZGC","zgc"),
 ("고독스","godox"),("웨스캇","westcott"),("브레스","broncolor"),("[주문제작]","_custom"),("주문제작","_custom"),
 ("디조필름","dzofilm"),("디죠필름","dzofilm"),("카세","kase"),("비스고","visgo"),("티비로직","tvlogic"),
 ("타이포크","typhoon"),("오픈문","openmoon"),("로데","rode"),("삼양","samyang"),("테라덱","teradek"),
 ("에디캠","edicam"),("어벤져","avenger"),("데스뷰","desview"),("로보컵","robocup"),("줌","zoom"),
 ("카텔로","cartello"),("아이풋티지","ifootage"),("아토모스","atomos"),("프로게퍼","progaffer"),
 ("앨빈스케이블","alvin"),("노가","noga"),("파나소닉","panasonic"),("파싱","pashing"),
]
def brand_of(name):
    n=re.sub(r"^(\[[^\]]*\]\s*)+","",name).strip()   # 앞 [재고보유]등 태그 제거
    for ko,slug in BRANDS:
        if n.startswith(ko) or n.replace(" ","").startswith(ko):
            return ko, slug
    return "_기타","_misc"

def get(u):
    r=S.get(u,timeout=30); r.encoding=r.apparent_encoding or "utf-8"; return r
def clean(t): return re.sub(r"\s+"," ",(t or "").strip())
def price_num(t):
    m=re.findall(r"[\d,]{3,}",clean(t)); return int(m[0].replace(",","")) if m else 0
def absu(u):
    if not u: return ""
    if u.startswith("//"): return "https:"+u
    if u.startswith("/"): return BASE+u
    return u

def list_products(cate_no, max_pages=6):
    out=[]
    for page in range(1,max_pages+1):
        soup=BeautifulSoup(get(f"{BASE}/product/list.html?cate_no={cate_no}&page={page}").text,"html.parser")
        items=soup.select("ul.prdList > li, li[id*='anchorBox']")
        got=0
        for li in items:
            a=li.select_one("a[href*='/product/']");
            if not a: continue
            m=re.search(r"/product/[^/]+/(\d+)/",a.get("href",""))
            if not m: continue
            ne=li.select_one(".name a, strong.name, .description .name")
            nm=clean(ne.get_text()) if ne else clean(a.get("title") or "")
            nm=re.sub(r"^상품명\s*:?\s*","",nm)
            pe=li.select_one(".price, span.price")
            out.append({"sid":m.group(1),"name":nm,
                        "price":price_num(pe.get_text()) if pe else 0,
                        "url":absu(a.get("href"))})
            got+=1
        if got==0: break
        time.sleep(0.5)
    seen={};
    for p in out: seen.setdefault(p["sid"],p)
    return list(seen.values())

def detail_images(url):
    soup=BeautifulSoup(get(url).text,"html.parser")
    def src(i): return absu(i.get("src") or i.get("ec-data-src") or i.get("data-src"))
    main=[src(i) for i in soup.select(".keyImg img")]
    add=[src(i) for i in soup.select(".listImg img, .xans-product-addimage img, .thumbnail li img")]
    det=[src(i) for i in soup.select("#prdDetail img, .cont img, .xans-product-detail img, #detail img")]
    def uniq(xs):
        s=[]; [s.append(x) for x in xs if x and x not in s]; return s
    return uniq(main+add), uniq(det)   # (대표+갤러리, 상세)

def to_webp(img_bytes, maxw, q=82):
    im=Image.open(io.BytesIO(img_bytes)).convert("RGB")
    if im.width>maxw:
        im=im.resize((maxw,int(im.height*maxw/im.width)),Image.LANCZOS)
    b=io.BytesIO(); im.save(b,"WEBP",quality=q,method=6); return b.getvalue()

def r2_exists(key):
    try: S3.head_object(Bucket=BUCKET,Key=key); return True
    except Exception: return False

def r2_put(key, data):
    S3.put_object(Bucket=BUCKET,Key=key,Body=data,ContentType="image/webp",
                  CacheControl="public,max-age=31536000,immutable")
    return f"{PUBLIC}/{key}"

def process(cate_no, category_name, limit=None):
    prods=list_products(cate_no)
    if limit: prods=prods[:limit]
    print(f"[{category_name}/{cate_no}] 리스트 {len(prods)}개 처리")
    by_brand={}
    for i,p in enumerate(prods,1):
        ko,slug=brand_of(p["name"])
        pid=f"clmedia-{p['sid']}"
        main,det=detail_images(p["url"])
        rec={"id":pid,"source":"clmedia","source_id":p["sid"],"name":p["name"],
             "brand":ko,"brand_slug":slug,"category":category_name,"cat_path":[category_name],
             "price":p["price"],"source_url":p["url"],
             "images":{"thumb":"","main":[],"detail":[]}}
        # 썸네일 = 대표 첫장
        thumb_src = main[0] if main else (add[0] if add else "")
        def upl(src, key, maxw):
            if not src or src.startswith("data:"): return ""
            if r2_exists(key): return f"{PUBLIC}/{key}"
            try:
                r=get(src); ct=r.headers.get("Content-Type","")
                if "image" not in ct or len(r.content)<900: return ""   # 스페이서/비이미지 스킵
                return r2_put(key, to_webp(r.content,maxw))
            except Exception: return ""
        if thumb_src:
            rec["images"]["thumb"]=upl(thumb_src, f"shop/thumbnails/{slug}/{pid}.webp", 600)
        for n,src in enumerate(main,1):
            u=upl(src, f"shop/images/{slug}/{pid}/main_{n}.webp", 1600)
            if u: rec["images"]["main"].append(u)
        for n,src in enumerate(det,1):
            u=upl(src, f"shop/detail/{slug}/{pid}/{n:02d}.webp", 1400)
            if u: rec["images"]["detail"].append(u)
        by_brand.setdefault(slug,{"brand":ko,"brand_slug":slug,"products":{}})
        by_brand[slug]["products"][pid]=rec
        print(f"  {i}/{len(prods)} [{ko}] {p['name'][:34]:<34} {p['price']:>9,}  main{len(rec['images']['main'])} det{len(rec['images']['detail'])}")
        time.sleep(0.4)
    # 브랜드별 JSON 병합저장
    for slug,pack in by_brand.items():
        fp=DATA/f"{slug}.json"
        if fp.exists():
            old=json.load(open(fp,encoding="utf-8")); old.setdefault("products",{}).update(pack["products"]); pack=old|{"products":old["products"]}
        json.dump(pack,open(fp,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
        print(f"  → data/products/{slug}.json ({len(pack['products'])}개)")
    # 미리보기 URL 출력
    print("\n=== 미리보기(R2) ===")
    for slug,pack in by_brand.items():
        for pid,rec in list(pack["products"].items())[:3]:
            print(f"  {rec['name'][:30]}  {rec['images']['thumb']}")

if __name__=="__main__":
    cate=sys.argv[1] if len(sys.argv)>1 else "207"
    lim=int(sys.argv[2]) if len(sys.argv)>2 else None
    names={"207":"Lighting","136":"Camera","163":"Lenses/Filters","184":"CameraSupport",
           "227":"Grip","239":"Monitor","254":"Audio","262":"촬영용품"}
    process(cate, names.get(cate,cate), lim)
