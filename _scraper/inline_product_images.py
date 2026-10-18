"""Preserve verified raster data-URI product descriptions as immutable assets."""
import base64
import hashlib
from io import BytesIO
from pathlib import Path
import re
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
PREFIX='assets/shop/supplier-details/'
PUBLIC='https://shop.nadaun.co/'


def materialize(value,source,root=None):
    if not re.fullmatch(r'[a-z0-9-]+',source):raise ValueError('Invalid inline image source')
    match=re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=\s]+)',value)
    if not match or len(value)>20_000_000:raise ValueError('Unsupported inline product image')
    raw=base64.b64decode(re.sub(r'\s','',match[2]),validate=True)
    with Image.open(BytesIO(raw)) as im:
        if im.format.lower()!=match[1] or min(im.size)<64 or im.width*im.height>60_000_000:
            raise ValueError('Invalid inline product image format or dimensions')
        im.verify()
    suffix='jpg' if match[1]=='jpeg' else match[1]
    digest=hashlib.sha256(raw).hexdigest()
    relative=PREFIX+source+'/'+digest+'.'+suffix
    target=Path(root or ROOT)/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if target.read_bytes()!=raw:raise ValueError('Inline product asset hash collision')
    else:target.write_bytes(raw)
    return PUBLIC+relative


def referenced_paths(products,details):
    found=set()
    for p in products:
        for url in details[p['detail_bucket']][p['id']].get('images',{}).get('detail',[]):
            if url.startswith(PUBLIC+PREFIX):
                relative=url.removeprefix(PUBLIC)
                if not re.fullmatch(re.escape(PREFIX)+r'[a-z0-9-]+/[a-f0-9]{64}\.(?:jpg|png|webp)',relative):
                    raise ValueError('Invalid immutable inline image path')
                found.add(relative)
    return sorted(found)
