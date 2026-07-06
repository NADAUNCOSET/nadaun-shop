# -*- coding: utf-8 -*-
"""히어로 배너 업로더 — PC(1920x400) + 모바일(750x600) 한 세트를 webp로 변환 후 R2 업로드.
   사용: python banner_upload.py <slug> <PC.jpg> <모바일.jpg>
   결과: media.nadaun.co/shop/banner/<slug>-pc.webp / -mob.webp URL + index.html 붙여넣기 스니펫 출력.
   스니펫엔 --fill(배너 좌/우 가장자리 색 자동추출 그라데이션)까지 포함 → 넓은 화면 양옆 배경이 배너와 자연 연결.
   ⚠️ R2 immutable 캐시: 같은 slug로 배너 교체 시 옛 이미지가 1년 서빙됨 → 배너 바뀌면 slug(날짜) 새로.
   실행 예: python banner_upload.py 20260418-osmo-pocket4 osmo-pc.jpg osmo-mob.jpg"""
import sys, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from PIL import Image
sys.path.insert(0, r"\\Nadaunproject\nadaunproject\_DAVINCI NADAUN PROJECT\_claude\jellyfin_proxy\_r2")
from _r2_common import client, BUCKET

S3 = client()
PUBLIC = "https://media.nadaun.co"

def to_webp(path, q=88):
    im = Image.open(path).convert("RGB")
    b = io.BytesIO(); im.save(b, "WEBP", quality=q, method=6)
    return b.getvalue(), im.size

def edge_colors(path, strip=6):
    """배너 좌/우 끝 세로줄 평균색 → (#left,#right). 양옆 배경 그라데이션에 사용."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    def avg(box):
        px = list(im.crop(box).getdata())
        n = len(px)
        r = sum(p[0] for p in px)//n; g = sum(p[1] for p in px)//n; bl = sum(p[2] for p in px)//n
        return f"#{r:02x}{g:02x}{bl:02x}"
    return avg((0, 0, strip, h)), avg((w-strip, 0, w, h))

def r2_put(key, data):
    S3.put_object(Bucket=BUCKET, Key=key, Body=data, ContentType="image/webp",
                  CacheControl="public,max-age=31536000,immutable")
    return f"{PUBLIC}/{key}"

def main():
    slug, pc_path, mob_path = sys.argv[1], sys.argv[2], sys.argv[3]
    urls = {}
    for tag, path in (("pc", pc_path), ("mob", mob_path)):
        data, size = to_webp(path)
        key = f"shop/banner/{slug}-{tag}.webp"
        url = r2_put(key, data)
        urls[tag] = url
        print(f"  {tag.upper():3} {size[0]}x{size[1]}  {len(data)//1024}KB  → {url}")
    lc, rc = edge_colors(pc_path)
    fill = f"linear-gradient(90deg,{lc} 0%,{lc} 42%,{rc} 58%,{rc} 100%)"
    print(f"  FILL 좌={lc} 우={rc}")
    print("\n── index.html 슬라이드 스니펫 ──")
    print(f'  <div class="hero-slide" style="--pc:url(\'{urls["pc"]}\');'
          f'--mob:url(\'{urls["mob"]}\');--fill:{fill}"></div>')

if __name__ == "__main__":
    main()
