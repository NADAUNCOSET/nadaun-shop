# -*- coding: utf-8 -*-
"""_misc.json 제품을 갱신된 브랜드별칭으로 재분류 + R2 이미지 서버복사(재다운X)."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"\\Nadaunproject\nadaunproject\_Site\nadaun-shop\_scraper")
import clmedia as C
from brands_map import brand_of   # 공용맵 (2026-07-11 보강: 영문표기+태그매칭) — clmedia 내장맵 대신 사용
DATA = C.DATA
fp = DATA/"_misc.json"
misc = json.load(open(fp, encoding="utf-8"))

def movekey(url, slug):
    if not url: return url
    key = url.replace(C.PUBLIC+"/","")
    newkey = key.replace("/_misc/","/"+slug+"/")
    if newkey==key: return url
    try:
        C.S3.copy_object(Bucket=C.BUCKET, CopySource={"Bucket":C.BUCKET,"Key":key}, Key=newkey,
                         MetadataDirective="REPLACE", ContentType="image/webp",
                         CacheControl="public,max-age=31536000,immutable")
        C.S3.delete_object(Bucket=C.BUCKET, Key=key)
    except Exception as e:
        print("   !copy",e)
    return C.PUBLIC+"/"+newkey

moved={}; keep={}
for pid, rec in misc["products"].items():
    ko, slug = brand_of(rec["name"])
    if slug=="_misc": keep[pid]=rec; continue
    rec["brand"]=ko; rec["brand_slug"]=slug
    im=rec["images"]
    im["thumb"]=movekey(im["thumb"],slug)
    im["main"]=[movekey(u,slug) for u in im["main"]]
    im["detail"]=[movekey(u,slug) for u in im["detail"]]
    moved.setdefault(slug,[]).append((pid,rec))

for slug, items in moved.items():
    bf=DATA/f"{slug}.json"
    pack=json.load(open(bf,encoding="utf-8")) if bf.exists() else {"brand":items[0][1]["brand"],"brand_slug":slug,"products":{}}
    for pid,rec in items: pack["products"][pid]=rec
    json.dump(pack,open(bf,"w",encoding="utf-8"),ensure_ascii=False,indent=2)

misc["products"]=keep
json.dump(misc,open(fp,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
print(f"재분류 이동 {sum(len(v) for v in moved.values())}개, _기타 잔여 {len(keep)}개")
for slug,items in sorted(moved.items(),key=lambda x:-len(x[1])): print(f"  {items[0][1]['brand']} ({slug}) +{len(items)}")
