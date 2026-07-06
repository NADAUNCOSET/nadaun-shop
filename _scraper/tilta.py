# -*- coding: utf-8 -*-
"""tilta.com(WooCommerce) → 나다운샵. 공개 Store API(/wp-json/wc/store/v1/products) JSON.
   전 제품(약 2027개) 이름·USD가격·이미지·카테고리. 이미지 webp→R2. brand=틸타 고정.
   실행: python tilta.py [LIMIT]   (LIMIT 없으면 전체)"""
import sys, io, re, json, time, html
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import requests
from bs4 import BeautifulSoup
from PIL import Image
sys.path.insert(0, r"\\Nadaunproject\nadaunproject\_DAVINCI NADAUN PROJECT\_claude\jellyfin_proxy\_r2")
from _r2_common import client, BUCKET
S3=client(); PUBLIC="https://media.nadaun.co"
DATA=Path(r"\\Nadaunproject\nadaunproject\_DAVINCI NADAUN PROJECT\_Site\nadaun-shop\data\products"); DATA.mkdir(parents=True,exist_ok=True)
API="https://tilta.com/wp-json/wc/store/v1/products"
S=requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64) Chrome/149 Safari/537.36"})

def clean(t): return re.sub(r"\s+"," ",html.unescape(t or "").strip())
def to_webp(b,maxw,q=82):
    im=Image.open(io.BytesIO(b)).convert("RGB")
    if im.width>maxw: im=im.resize((maxw,int(im.height*maxw/im.width)),Image.LANCZOS)
    o=io.BytesIO(); im.save(o,"WEBP",quality=q,method=6); return o.getvalue()
def r2_has(k):
    try: S3.head_object(Bucket=BUCKET,Key=k); return True
    except Exception: return False
def upl(src,key,maxw):
    if not src: return ""
    if r2_has(key): return f"{PUBLIC}/{key}"
    try:
        r=S.get(src,timeout=30);
        if "image" not in r.headers.get("Content-Type","") or len(r.content)<900: return ""
        S3.put_object(Bucket=BUCKET,Key=key,Body=to_webp(r.content,maxw),ContentType="image/webp",
                      CacheControl="public,max-age=31536000,immutable")
        return f"{PUBLIC}/{key}"
    except Exception: return ""

def fetch_all(limit=None):
    prods=[]; page=1
    while True:
        r=S.get(API,params={"per_page":100,"page":page},timeout=40)
        if r.status_code!=200: break
        d=r.json()
        if not d: break
        prods+=d
        tp=int(r.headers.get("X-WP-TotalPages",1))
        print(f"  API page {page}/{tp} (+{len(d)}, 누적 {len(prods)})")
        if limit and len(prods)>=limit: prods=prods[:limit]; break
        if page>=tp: break
        page+=1; time.sleep(0.3)
    return prods

def run(limit=None):
    raw=fetch_all(limit)
    print(f"수집 {len(raw)}개 처리 시작")
    fp=DATA/"tilta.json"
    pack=json.load(open(fp,encoding="utf-8")) if fp.exists() else {"brand":"틸타","brand_slug":"tilta","products":{}}
    for i,p in enumerate(raw,1):
        pid=f"tiltacom-{p['id']}"
        cats=[clean(c["name"]) for c in p.get("categories",[])]
        imgs=[im.get("src") for im in p.get("images",[]) if im.get("src")]
        # 상세이미지 = description HTML의 img
        det=[im.get("src") for im in BeautifulSoup(p.get("description",""),"html.parser").select("img") if im.get("src")]
        rec={"id":pid,"source":"tilta.com","source_id":str(p["id"]),
             "name":clean(p.get("name")),"brand":"틸타","brand_slug":"tilta",
             "category":cats[0] if cats else "","cat_path":cats,
             "price":0,"price_usd":round(int(p.get("prices",{}).get("price",0))/100,2),
             "sku":p.get("sku",""),"source_url":p.get("permalink",""),
             "images":{"thumb":"","main":[],"detail":[]}}
        if imgs:
            rec["images"]["thumb"]=upl(imgs[0],f"shop/thumbnails/tilta/{pid}.webp",600)
            for n,s in enumerate(imgs,1):
                u=upl(s,f"shop/images/tilta/{pid}/main_{n}.webp",1600)
                if u: rec["images"]["main"].append(u)
        for n,s in enumerate(det,1):
            u=upl(s,f"shop/detail/tilta/{pid}/{n:02d}.webp",1400)
            if u: rec["images"]["detail"].append(u)
        pack["products"][pid]=rec
        if i%20==0 or i<=15:
            print(f"  {i}/{len(raw)} {rec['name'][:40]:<40} ${rec['price_usd']}  img{len(rec['images']['main'])}")
        if i%50==0:   # 중간 저장(대량 대비)
            json.dump(pack,open(fp,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    json.dump(pack,open(fp,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print(f"완료: tilta.json 총 {len(pack['products'])}개")

if __name__=="__main__":
    lim=int(sys.argv[1]) if len(sys.argv)>1 else None
    run(lim)
