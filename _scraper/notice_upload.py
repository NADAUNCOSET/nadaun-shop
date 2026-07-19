# -*- coding: utf-8 -*-
r"""[상세페이지 고정 안내문 업로더] 상단/하단 고정 안내문 이미지 → R2 shop/notice/<slug>.webp.

안내문은 텍스트 그래픽이라 화질 유지가 중요 → webp method=6, 텍스트 선명도 위해 quality 92
(플랫컬러라 용량도 작음). 표시 폭(≤820px) 대비 레티나 위해 폭 1080 상한만 다운스케일.
캐시는 1일(max-age=86400) — 안내문은 문구 수정 가능성 있어 immutable 대신 짧게(같은 URL 갱신 허용).

사용: python notice_upload.py <slug> "<이미지경로>"
예:   python notice_upload.py return-policy "\\Nadaundata\...\상단 고정 안내문\반품불가_안내.jpg"
결과: media.nadaun.co/shop/notice/<slug>.webp URL 출력.
"""
import sys, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from PIL import Image
sys.path.insert(0, r"\\Nadaunproject\nadaunproject\_claude\jellyfin_proxy\_r2")
from _r2_common import client, BUCKET

S3 = client()
PUBLIC = "https://media.nadaun.co"
MAXW = 1080

def to_webp(path, q=92):
    im = Image.open(path).convert("RGB")
    if im.width > MAXW:
        im = im.resize((MAXW, round(im.height * MAXW / im.width)), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, "WEBP", quality=q, method=6)
    return b.getvalue(), im.size

def main():
    slug, path = sys.argv[1], sys.argv[2]
    data, size = to_webp(path)
    key = f"shop/notice/{slug}.webp"
    S3.put_object(Bucket=BUCKET, Key=key, Body=data, ContentType="image/webp",
                  CacheControl="public,max-age=86400")
    url = f"{PUBLIC}/{key}"
    print(f"  {slug}  {size[0]}x{size[1]}  {len(data)//1024}KB  → {url}")

if __name__ == "__main__":
    main()
