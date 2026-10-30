"""Refresh the reviewed FUNOMAD families, with explicit source-scope checks.

The source advertises product families as well as individual models. A menu
change is saved for review instead of inventing unverified manufacturer SKUs.
"""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urljoin,urlsplit,urlunsplit
from datetime import datetime,timezone
import hashlib,json,re
from bs4 import BeautifulSoup
from reviewed_supplier_sources import validate_snapshot,ids_digest
from mirror_schedule import atomic_json

RECIPE=Path(__file__).with_name('funomad-reviewed-families.json')

def canonical(url):
    p=urlsplit(url)
    if p.hostname!='funomad.com' or p.query or p.fragment:return None
    return urlunsplit(('https','funomad.com',p.path.rstrip('/')+'/', '', ''))

def navigation(raw):
    doc=BeautifulSoup(raw,'lxml');node=doc.select_one('nav.et-menu-nav > ul')
    if node is None:raise ValueError('FUNOMAD source navigation missing')
    def visit(ul,parents=()):
        result=[]
        for li in ul.find_all('li',recursive=False):
            a=li.find('a',recursive=False)
            if not a:continue
            label=a.get_text(' ',strip=True);trail=(*parents,label)
            result.append({'label':label,'path':list(trail),'url':canonical(a.get('href',''))})
            child=li.find('ul',recursive=False)
            if child:result+=visit(child,trail)
        return result
    return visit(node)

def originals(body,url):
    images=[]
    for img in body.select('img'):
        choices=[]
        for key,rank in [('src',0),('data-src',1),('data-original',10**9)]:
            value=img.get(key,'')
            if value and not value.startswith('data:'):choices.append((rank,urljoin(url,value)))
        for key in ('srcset','data-srcset'):
            for part in img.get(key,'').split(','):
                bits=part.strip().split()
                if bits:
                    rank=float(re.sub('[^0-9.]','',bits[-1]) or '0') if len(bits)>1 else 0
                    choices.append((rank,urljoin(url,bits[0])))
        if choices:images.append(max(choices)[1])
    return list(dict.fromkeys(images))

def verify_page(raw,url,rows):
    doc=BeautifulSoup(raw,'lxml');body=doc.select_one('.entry-content')
    if body is None:raise ValueError('FUNOMAD product body missing: '+url)
    images=set(originals(body,url));all_observed={urljoin(url,tag[key]) for tag in body.select('img') for key in ('src','data-src','data-original') if tag.get(key) and not tag[key].startswith('data:')}
    for row in rows:
        for image in row['images']:
            if urlsplit(image).hostname=='funomad.com' and image not in images|all_observed:
                raise ValueError('FUNOMAD reviewed product image changed; exact model/image review required: '+row['id'])
    return hashlib.sha256(raw).hexdigest()

def collect(client,previous):
    recipe=json.loads(RECIPE.read_text());home=client.get('https://funomad.com/');menu=navigation(home)
    atomic_json(client.folder/'navigation.json',menu)
    if menu!=recipe['navigation']:
        atomic_json(client.folder/'navigation-change.json',{'previous':recipe['navigation'],'current':menu,'requires_review':True})
        raise ValueError('FUNOMAD menu changed; new product/category identities need review')
    rows_by_url={}
    for row in recipe['products']:rows_by_url.setdefault(row['url'],[]).append(row)
    pages={};observations={}
    urls=list(dict.fromkeys([m['url'] for m in menu if m['url']]+list(rows_by_url)))
    for url in urls:
        raw=client.get(url,allow_missing=url not in rows_by_url)
        if raw is None:
            observations[url]={'status':404,'excluded_from_product_rows':True};continue
        doc=BeautifulSoup(raw,'lxml')
        if doc.select_one('.entry-content') is None:raise ValueError('FUNOMAD linked page body is missing')
        if url in rows_by_url:pages[url]=verify_page(raw,url,rows_by_url[url])
        observations[url]={'status':200,'sha256':hashlib.sha256(raw).hexdigest()}
    products={};images={};checked=datetime.now(timezone.utc).isoformat()
    expected={'funomad-'+r['id'] for r in recipe['products']}
    if expected!=set(previous['products']):raise ValueError('FUNOMAD reviewed family baseline differs from published source')
    for row in recipe['products']:
        product=deepcopy(previous['products']['funomad-'+row['id']])
        for url in row['images']:
            if url not in images:images[url]=client.image(url)
        urls=[images[u] for u in row['images']]
        product.update(price=None,sale_price=None,status='inquiry',supplier_status='inquiry',
            detail_checked_at=checked,detail_status='verified',evidence_sha256=pages[row['url']],
            images={'thumb':urls[0],'main':[urls[0]],'detail':urls[1:] or [urls[0]]})
        if any(o.get('price') is not None for o in product.get('options',[])):raise ValueError('FUNOMAD inquiry option gained a price')
        products[product['id']]=product
    snapshot=deepcopy(previous);snapshot.update(collected_at=checked,complete=True,products=products,product_count=len(products),
        coverage={'count':len(products),'ids_sha256':ids_digest(products)},
        evidence={'pages_verified':len(observations),'original_images':len(images),'reviewed_product_or_family_rows':len(products),
            'manufacturer_full_sku_inventory':False,'navigation_verified':len(menu),'scope':recipe['scope'],'page_observations':observations})
    validate_snapshot(snapshot)
    return snapshot
