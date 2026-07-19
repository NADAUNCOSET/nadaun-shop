# -*- coding: utf-8 -*-
"""KPP(kppkpp.co.kr, 영카트) → 나다운샵 제품DB 파이프라인.
   카테고리(ca_id)별 전수 스크랩. KPP 정식 대>중>소 분류 = shop.nadaun.co SoT(taxonomy_kpp.md).
   리스트(list.php?ca_id=..&page=N) → 상세(item.php?it_id=..) → 정가 캡처 → webp → R2 → 브랜드별 JSON.
   stable id = kpp-<it_id>. 이미 R2에 있으면 skip(증분).
   규칙: 가격=정가(cut_price 소비자가 우선, 없으면 itt_price). 정확도 최우선(단종 판별은 대표 육안검수).

   실행:
     python kpp.py NAV                 # 카테고리 트리만 덤프(확인용)
     python kpp.py <ca_id> [LIMIT]     # 한 카테고리 파일럿 (예: 0220 5)
     python kpp.py ALL [LIMIT_PER_CAT] # 전 leaf 카테고리 전체
"""
import sys, io, re, json, time, socket
from pathlib import Path
socket.setdefaulttimeout(60)   # 행 방지: 모든 소켓(요청·이미지CDN·R2 boto3) 60s 상한 (2026-07-08 14분 행 사고)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import requests
from bs4 import BeautifulSoup
from PIL import Image

# R2 (jellyfin _r2_common 재사용)
sys.path.insert(0, r"\\Nadaunproject\nadaunproject\_claude\jellyfin_proxy\_r2")
from _r2_common import client, BUCKET
S3 = client()
PUBLIC = "https://media.nadaun.co"

ROOT = Path(r"\\Nadaunproject\nadaunproject\_Site\nadaun-shop")
DATA = ROOT/"data"/"products"; DATA.mkdir(parents=True, exist_ok=True)

BASE = "https://www.kppkpp.co.kr"
UA_H = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36"}
S = requests.Session(); S.headers.update(UA_H)

# 브랜드 한글/영문 접두 → 슬러그. 미매칭 → _기타 (대표 육안검수에서 보정)
BRANDS = [
 ("스몰리그","smallrig"),("SmallRig","smallrig"),("틸타","tilta"),("Tilta","tilta"),
 ("레오포토","leofoto"),("Leofoto","leofoto"),("어퓨처","aputure"),("어퓨쳐","aputure"),("아마란","aputure"),
 ("아리","arri"),("홀리랜드","hollyland"),("난라이트","nanlite"),("난룩스","nanlux"),("프로포토","profoto"),
 ("소니","sony"),("캐논","canon"),("니콘","nikon"),("후지","fujifilm"),("파나소닉","panasonic"),
 ("디제이아이","dji"),("DJI","dji"),("라오와","laowa"),("젠하이저","sennheiser"),("슈어","shure"),
 ("니시","nisi"),("NISI","nisi"),("쿠포","kupo"),("젠트리","gentree"),("이지리그","easyrig"),
 ("맨프로토","manfrotto"),("삭틀러","sachtler"),("자이스","zeiss"),("블랙매직","blackmagic"),
 ("호크우드","hawkwood"),("모션9","motion9"),("노바칩스","novachips"),("기트조","gitzo"),
 ("퀄라이트","qualite"),("오스람","osram"),("잭커리","jackery"),("아스테라","astera"),
 ("에프엑스리온","fxlion"),("FXLION","fxlion"),("나이트코어","nitecore"),("아트뮤","artmu"),
 ("ZGCINE","zgcine"),("ZGC","zgc"),("고독스","godox"),("웨스캇","westcott"),("브레스","broncolor"),
 ("디조필름","dzofilm"),("디죠필름","dzofilm"),("디죠","dzofilm"),("조프","dzofilm"),
 ("카세","kase"),("비스고","visgo"),("티비로직","tvlogic"),("타이포크","typhoon"),("오픈문","openmoon"),
 ("로데","rode"),("삼양","samyang"),("테라덱","teradek"),("에디캠","edicam"),("어벤져","avenger"),
 ("데스뷰","desview"),("로보컵","robocup"),("줌","zoom"),("카텔로","cartello"),("아이풋티지","ifootage"),
 ("아토모스","atomos"),("프로게퍼","progaffer"),("앨빈스케이블","alvin"),("노가","noga"),
 # KPP 브랜드몰 위젯 노출 브랜드
 ("호야","hoya"),("HOYA","hoya"),("토키나","tokina"),("TOKINA","tokina"),
 ("빌트록스","viltrox"),("VILTROX","viltrox"),("피지테크","pgytech"),("PGYTECH","pgytech"),
 ("티티아티산","ttartisan"),("TTArtisan","ttartisan"),("완더드","wandrd"),("WANDRD","wandrd"),
 ("지테이","zitay"),("ZITAY","zitay"),("아스트호리","astrhori"),("ASTRHORI","astrhori"),
 ("에이치앤와이","hy"),("H&Y","hy"),("맷세스","matthews"),("아르카스위스","arcaswiss"),("HOYA","hoya"),
 ("[주문제작]","_custom"),("주문제작","_custom"),
]

# 상세영역 배너/보일러플레이트(제품컷 아님) — esmplus/공통 이미지 제외 키워드
DETAIL_BLOCK = ("interest_free","join_benefit","auth_benefit","/delivery/","_cate","/event",
    "notice","brand_event","brand_notice","cate_event","product_event","as_guide",
    "brand_logo","/benefit","/banner","top_banner","bottom_banner")
def is_detail(u):
    if not u or u.startswith("data:"): return False
    ok = ("/data/item/" in u) or ("esmplus.com" in u)
    return ok and not any(b in u.lower() for b in DETAIL_BLOCK)
def brand_of(name):
    n=re.sub(r"^(\[[^\]]*\]\s*)+","",name).strip()   # 앞 [신품]/[재고보유] 등 태그 제거
    nn=n.replace(" ","")
    for ko,slug in BRANDS:
        if n.startswith(ko) or nn.startswith(ko.replace(" ","")):
            return ko, slug
    return "_기타","_misc"

import threading
def _fetch_one(u, out):
    try: out.append(S.get(u, timeout=30))
    except Exception as e: out.append(e)

def get(u, retries=3, deadline=50):
    """절대 데드라인 get — 타르핏 드립피드(찔끔찔끔 응답)가 read-timeout을 회피해도
    deadline초 지나면 포기하고 새 세션으로 재시도 (2026-07-09 대형 카테고리 리스트 행 대응)."""
    global S
    for k in range(retries):
        out=[]
        t=threading.Thread(target=_fetch_one,args=(u,out),daemon=True)
        t.start(); t.join(deadline)
        if out and not isinstance(out[0],Exception):
            r=out[0]
            ct=r.headers.get("Content-Type","")
            if "text" in ct or "html" in ct or "json" in ct:   # 이미지 등 바이너리에 chardet 돌면 수분 행 (2026-07-09)
                r.encoding=r.apparent_encoding or "utf-8"
            return r
        S=requests.Session(); S.headers.update(UA_H)   # 행/에러 → 세션 갈아끼움
        if k==retries-1: raise RuntimeError(f"get 데드라인 초과/실패: {u}")
        time.sleep(2*(k+1))
def clean(t): return re.sub(r"\s+"," ",(t or "").strip())
def price_num(t):
    m=re.findall(r"[\d,]{3,}",clean(t)); return int(m[0].replace(",","")) if m else 0
def absu(u):
    if not u: return ""
    u=u.replace("\\","/")
    if u.startswith("//"): return "https:"+u
    if u.startswith("../"): return BASE+"/"+u[3:]
    if u.startswith("/"): return BASE+u
    if u.startswith("http"): return u
    return BASE+"/"+u.lstrip("./")

# ── 카테고리 네비 ───────────────────────────────────────────────
def fetch_nav():
    """KPP 카테고리 메뉴 파싱 → {ca_id: name}. leaf = 다른 ca_id의 접두가 아닌 것."""
    soup=BeautifulSoup(get(f"{BASE}/shop/list.php").text,"html.parser")
    cats={}
    for a in soup.select('a[href*="list.php?ca_id="]'):
        m=re.search(r"ca_id=([0-9a-z]+)",a.get("href",""))
        if not m: continue
        cid=m.group(1); nm=clean(a.get_text()).lstrip("#")
        if nm and (cid not in cats or len(cats[cid])<2):
            cats[cid]=nm
    return cats

def leaves_of(cats):
    ids=list(cats.keys())
    leaves=[c for c in ids if not any(o!=c and o.startswith(c) for o in ids)]
    return sorted(leaves)

def cat_path_of(cid, cats):
    """cid의 상위 체인 이름 리스트 (대>중>소). 접두인 ca_id들을 길이순."""
    anc=sorted([c for c in cats if cid.startswith(c)], key=len)
    return [cats[c] for c in anc]

# ── 리스트 ─────────────────────────────────────────────────────
def list_items(ca_id, max_pages=200):
    """⚠️ 반드시 메인 리스트 컨테이너(#sct li.sct_li)만 — 페이지 밖 '오늘 본 상품' 등
    쿠키 위젯의 it_id를 잡으면 타 카테고리 상품이 오염 수집됨(2026-07-08 사고)."""
    seen=[]
    for page in range(1,max_pages+1):
        soup=BeautifulSoup(get(f"{BASE}/shop/list.php?ca_id={ca_id}&page={page}").text,"html.parser")
        ids=[]
        for li in soup.select("#sct li.sct_li"):
            a=li.select_one('a[href*="it_id="]')
            if not a: continue
            m=re.search(r"it_id=(\d+)",a.get("href",""))
            if m: ids.append(m.group(1))
        new=[i for i in dict.fromkeys(ids) if i not in seen]
        if not new: break
        seen+=new
        if page%10==0: print(f"  … 리스트 수집 p{page} ({len(seen)}개)",flush=True)  # 대형 카테고리 무응답 오판 방지 (2026-07-09 73/95 재시작루프)
        time.sleep(0.4)
    return seen

# ── 상세 ───────────────────────────────────────────────────────
def parse_item(it_id):
    url=f"{BASE}/shop/item.php?it_id={it_id}"
    soup=BeautifulSoup(get(url).text,"html.parser")
    # 이름 + 카테고리 (title: "제품명 > 카테고리 | 코리아포토프로덕츠(KPP)")
    title=clean(soup.title.get_text() if soup.title else "")
    name=title.split(" > ")[0].strip()
    og=soup.select_one('meta[property="og:title"]')
    if og and clean(og.get("content")): name=clean(og.get("content"))
    # 가격: 메인 상품 영역(.sit_price)만
    sit=soup.select_one(".sit_price")
    cut=price_num(sit.select_one(".cut_price").get_text()) if (sit and sit.select_one(".cut_price")) else 0
    itt_el=sit.select_one(".itt_price") if sit else None
    itt_txt=clean(itt_el.get_text()) if itt_el else ""
    itt=0 if "전화문의" in itt_txt else price_num(itt_txt)
    price=cut or itt          # 정가(소비자가) 우선, 없으면 판매가
    inquiry="전화문의" in itt_txt and cut==0
    # 이미지: 대표 og:image + 갤러리(#sit_pvi_thumb의 thumb-...→풀사이즈), 상세(#sit_inf_explan)
    ogimg=soup.select_one('meta[property="og:image"]')
    main=[]
    if ogimg and ogimg.get("content"): main.append(absu(ogimg.get("content")))
    for im in soup.select("#sit_pvi_thumb img, #sit_pvi_big img"):
        src=im.get("src") or ""
        full=re.sub(r"thumb-", "", src); full=re.sub(r"_\d+x\d+(?=\.\w+$)","",full)
        if "/data/item/" in full: main.append(absu(full))
    det=[]
    exp=soup.select_one("#sit_inf_explan")
    if exp:
        for im in exp.select("img"):
            src=im.get("src") or im.get("data-src") or im.get("ec-data-src") or ""
            if is_detail(src): det.append(absu(src))
    def uniq(xs):
        s=[];[s.append(x) for x in xs if x and x not in s and not x.startswith("data:")];return s
    return {"name":name,"price":price,"list_price":cut,"sale_price":itt,
            "inquiry":inquiry,"main":uniq(main),"detail":uniq(det),"url":url}

# ── 이미지 R2 ──────────────────────────────────────────────────
def to_webp(b, maxw, q=82):
    im=Image.open(io.BytesIO(b)).convert("RGB")
    if im.width>maxw: im=im.resize((maxw,int(im.height*maxw/im.width)),Image.LANCZOS)
    o=io.BytesIO(); im.save(o,"WEBP",quality=q,method=6); return o.getvalue()
def _bounded(fn, deadline, *a, **kw):
    """R2(boto3) 호출 절대 데드라인 — botocore 자체 재시도가 4분+ 침묵할 수 있어 스레드로 상한 (2026-07-09)."""
    out=[]
    def run():
        try: out.append(fn(*a,**kw))
        except Exception as e: out.append(e)
    t=threading.Thread(target=run,daemon=True); t.start(); t.join(deadline)
    if out and not isinstance(out[0],Exception): return out[0]
    raise RuntimeError(f"R2 op 데드라인/실패")

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
def process(ca_id, cats, limit=None):
    global S   # 카테고리마다 새 세션 — 장시간 연결 타르핏/쿠키누적 방지 (2026-07-08)
    S=requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36"})
    cname=cats.get(ca_id,ca_id); cpath=cat_path_of(ca_id,cats) or [cname]
    ids=list_items(ca_id)
    if limit: ids=ids[:limit]
    print(f"[{'/'.join(cpath)} · ca_id={ca_id}] 상품 {len(ids)}개")
    by_brand={}
    for i,it in enumerate(ids,1):
        try: d=parse_item(it)
        except Exception as e: print(f"  ! {it} 파싱실패 {e}"); continue
        ko,slug=brand_of(d["name"]); pid=f"kpp-{it}"
        rec={"id":pid,"source":"kpp","source_id":it,"name":d["name"],
             "brand":ko,"brand_slug":slug,"category":cname,"cat_path":cpath,
             "ca_id":ca_id,"price":d["price"],"list_price":d["list_price"],
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
            if n%5==0: print(f"    … 이미지 {n}/{len(d['detail'])}",flush=True)  # 이미지多·서버 스로틀 시 무응답 오판 방지
        by_brand.setdefault(slug,{"brand":ko,"brand_slug":slug,"products":{}})
        by_brand[slug]["products"][pid]=rec
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
    arg=sys.argv[1] if len(sys.argv)>1 else "NAV"
    cats=fetch_nav()
    if arg=="NAV":
        lv=leaves_of(cats)
        print(f"카테고리 {len(cats)}개, leaf {len(lv)}개")
        for c in lv: print(f"  {c:<8} {'/'.join(cat_path_of(c,cats))}")
    elif arg=="ALL":
        lim=int(sys.argv[2]) if len(sys.argv)>2 else None
        leaves=leaves_of(cats); tot={}; done=0
        ckpt=DATA.parent/"_kpp_done.json"   # 완료 카테고리 체크포인트(재시작 스킵)
        done_set=set(json.load(open(ckpt,encoding="utf-8"))) if ckpt.exists() else set()
        print(f"=== KPP 전체 스크랩 시작: leaf {len(leaves)}개 (완료스킵 {len(done_set)}) ===",flush=True)
        for c in leaves:
            if c in done_set:
                done+=1; continue
            try:
                bb=process(c,cats,lim)
                for s in bb: tot[s]=tot.get(s,0)+len(bb[s]["products"])
                done_set.add(c)
                json.dump(sorted(done_set),open(ckpt,"w",encoding="utf-8"))
            except Exception as e:
                print(f"  !! 카테고리 {c} 실패(스킵): {e}",flush=True)
            done+=1
            print(f"--- 진행 {done}/{len(leaves)} 카테고리, 누계상품 {sum(tot.values())} ---",flush=True)
            sys.stdout.flush()
        print("\n=== 완료 브랜드별 누계 ===",flush=True)
        for s,n in sorted(tot.items(),key=lambda x:-x[1]): print(f"  {s:<14} {n}",flush=True)
    else:
        lim=int(sys.argv[2]) if len(sys.argv)>2 else None
        process(arg,cats,lim)
