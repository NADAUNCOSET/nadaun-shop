"""Resize product previews from the official source without changing content."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from io import BytesIO
import json
from pathlib import Path
import re
from PIL import Image, ImageOps
from sync_shop_sources import ROOT,OUT,request,save_json
TARGET=ROOT/'assets/shop/thumbnails'

def prepare():
    products=json.loads((OUT/'imweb-dji.json').read_text())['products']
    TARGET.mkdir(parents=True,exist_ok=True)
    manifest_path=ROOT/'data/catalog/asset-manifest.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    jobs=[]
    for pid,p in products.items():
        url=p['images']['thumb'];saved=manifest.get(pid,{})
        if saved.get('source_url')==url and (ROOT/saved.get('path','missing')).is_file():continue
        jobs.append((pid,url))
    def work(job):
        pid,url=job;raw=request('GET',url).content
        im=ImageOps.exif_transpose(Image.open(BytesIO(raw))).convert('RGB');im.thumbnail((850,850),Image.Resampling.LANCZOS)
        filename=TARGET/(pid+'.webp');im.save(filename,'WEBP',quality=86,method=5)
        return pid,{'source_url':url,'path':filename.relative_to(ROOT).as_posix(),'width':im.width,'height':im.height}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(work,j) for j in jobs]
        for n,f in enumerate(as_completed(futures),1):
            pid,result=f.result();manifest[pid]=result
            if n%20==0:print('DJI thumbnails',n,'/',len(jobs),flush=True)
    save_json(manifest_path,manifest)
    print('DJI image previews verified:',len(manifest),flush=True)
    return manifest
if __name__=='__main__':prepare()
