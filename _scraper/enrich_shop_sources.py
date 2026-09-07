"""Fetch public product descriptions; cache only whitelisted storefront fields."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from sync_shop_sources import ROOT, OUT, NAVER, KPP, request, save_json, stamp, clean, naver_headers
from sync_kpp_catalog import fetch, won_values

CACHE = ROOT / 'data/catalog/source-details'

def shard(pid):
    return hashlib.sha256(pid.encode()).hexdigest()[:2]

def source_fingerprint(product):
    fields={k:product.get(k) for k in ('name','price','sale_price','supplier_status')}
    fields['thumb']=(product.get('images') or {}).get('thumb')
    return hashlib.sha256(json.dumps(fields,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def image_urls(content, base=''):
    urls=[]
    for img in content.select('img'):
        src=img.get('src') or img.get('data-src') or ''
        if src.startswith('//'): src='https:'+src
        elif src.startswith('http://'): src='https://'+src[7:]
        else: src=urljoin(base,src)
        if src.startswith('https://') and src not in urls: urls.append(src)
    return urls

def naver_detail(product, headers):
    body=request('GET',NAVER+'/v2/products/origin-products/'+product['origin_id'],headers=headers).json()
    origin=body.get('originProduct')
    if not origin or not origin.get('name'): raise RuntimeError('Invalid Naver product detail')
    content=BeautifulSoup(origin.get('detailContent',''),'lxml')
    for el in content.select('script,style'): el.decompose()
    images=origin.get('images') or {}
    main=[v.get('url') for v in [images.get('representativeImage',{})]+images.get('optionalImages',[]) if v.get('url','').startswith('https://')]
    options=(origin.get('detailAttribute') or {}).get('optionInfo') or {}
    groups=options.get('optionCombinationGroupNames') or {}
    # Preserve option labels/price increments without exposing stock or seller codes.
    choices=[]
    for option in options.get('optionCombinations',[]):
        if option.get('usable') is False: continue
        labels=[clean(option.get('optionName'+str(i))) for i in (1,2,3) if option.get('optionName'+str(i))]
        choices.append({'name':' / '.join(labels),'additional_price':option.get('price',0)})
    shipping=origin.get('deliveryInfo') or {}
    fee=shipping.get('deliveryFee') or {}
    return {'images':{'main':main,'detail':image_urls(content)},
            'description_text':content.get_text('\n',strip=True),
            'option_groups':[clean(v) for v in groups.values()], 'options':choices,
            'shipping':{'type':fee.get('deliveryFeeType'),'base_fee':fee.get('baseFee'),'free_threshold':fee.get('freeConditionalAmount')},
            'detail_status':'verified','source_modified_at':product.get('source_modified_at')}

def kpp_detail(product):
    soup=fetch(product['source_url'])
    og=soup.select_one('meta[property="og:title"]')
    price=soup.select_one('.sit_price')
    exp=soup.select_one('#sit_inf_explan')
    unavailable_message=next((m for m in ('현재 판매가능한 상품이 아닙니다','자료가 없습니다') if m in soup.get_text(' ',strip=True)),None)
    if unavailable_message:
        # The list can still advertise retired items. Confirm a second read;
        # this is an explicit source state, never a network failure/deletion.
        check=fetch(product['source_url'])
        if unavailable_message not in check.get_text(' ',strip=True):
            raise RuntimeError('KPP availability changed during verification')
        return {'detail_status':'verified','unavailable':True,'images':{'main':[],'detail':[]},'price':product.get('price'),'sale_price':product.get('sale_price')}
    if not soup.title or not price or not exp: raise RuntimeError('KPP detail is missing its product section')
    main=[]
    image=soup.select_one('meta[property="og:image"]')
    if image and image.get('content'): main.append(urljoin(KPP,image['content']))
    for im in soup.select('#sit_pvi_thumb img, #sit_pvi_big img'):
        url=urljoin(KPP,im.get('src',''))
        if '/data/item/' not in url: continue
        url=re.sub(r'thumb-','',url)
        url=re.sub(r'_\d+x\d+(?=\.\w+$)','',url)
        if url not in main: main.append(url)
    block=('interest_free','join_benefit','auth_benefit','/delivery/','/event','notice','as_guide','brand_logo','/benefit','/banner','top_banner','bottom_banner','/shop/images/')
    details=[u for u in image_urls(exp,KPP) if not any(b in u.lower() for b in block)] if exp else []
    original=won_values(price.select_one('.cut_price'))
    selling=won_values(price.select_one('.itt_price'))
    return {'images':{'main':main,'detail':details},'price':original[0] if original else selling[0] if selling else None,
            'sale_price':selling[0] if selling else None,'description_text':exp.get_text('\n',strip=True) if exp else '',
            'detail_status':'verified'}

def collect(source,limit=None,force=False):
    snapshot=json.loads((OUT/(source+'.json')).read_text())
    products=snapshot['products']
    folder=CACHE/source; folder.mkdir(parents=True,exist_ok=True)
    buckets={p.stem:json.loads(p.read_text()) for p in folder.glob('*.json') if re.fullmatch('[0-9a-f]{2}',p.stem)}
    pending=[]
    now=time.time()
    for pid,p in products.items():
        old=buckets.get(shard(pid),{}).get(pid,{})
        fresh=old.get('detail_status')=='verified' and old.get('source_modified_at')==p.get('source_modified_at')
        if source=='kpp': fresh=fresh and now-old.get('checked_epoch',0)<6*3600 and old.get('source_fingerprint')==source_fingerprint(p)
        if force or not fresh: pending.append(p)
    if limit: pending=pending[:limit]
    print(f'{source} detail: {len(pending):,} to read, {len(products):,} total',flush=True)
    headers=naver_headers() if source=='smartstore' and pending else None
    failures=[]; touched=set()
    def work(p):
        result=naver_detail(p,headers) if source=='smartstore' else kpp_detail(p)
        result['checked_at']=stamp(); result['checked_epoch']=int(time.time())
        if source=='kpp':result['source_fingerprint']=source_fingerprint(p)
        time.sleep(.12)
        return p['id'],result
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks={pool.submit(work,p):p['id'] for p in pending}
        for n,f in enumerate(as_completed(tasks),1):
            try:
                pid,result=f.result(); key=shard(pid)
                buckets.setdefault(key,{})[pid]=result; touched.add(key)
            except Exception as e:
                failures.append({'id':tasks[f],'error':str(e)})
                if len(failures)<=5: print(f'Detail error {tasks[f]}: {e}',flush=True)
            if n%100==0 or n==len(tasks):
                for key in touched: save_json(folder/(key+'.json'),buckets[key])
                touched.clear()
                print(f'{source} detail: {n:,}/{len(tasks):,}, errors {len(failures)}',flush=True)
    if failures:
        save_json(folder/'failures.json',{'failures':failures})
        raise RuntimeError(f'{source}: {len(failures)} details failed; cached progress preserved')
    if (folder/'failures.json').exists():
        save_json(folder/'failures.json',{'failures':[],'resolved_at':stamp()})
    verified=sum(1 for pid in products if buckets.get(shard(pid),{}).get(pid,{}).get('detail_status')=='verified')
    print(f'{source} detail verified: {verified:,}/{len(products):,}',flush=True)
    if not limit and verified!=len(products): raise RuntimeError('Incomplete source detail coverage')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',choices=['smartstore','kpp']);p.add_argument('--limit',type=int);p.add_argument('--force',action='store_true')
    a=p.parse_args();collect(a.source,a.limit,a.force)
