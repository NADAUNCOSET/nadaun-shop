"""Project the saved public gift inventory into an internal shop directory.

Reads inventory.sqlite3 in read-only mode. Never opens suppliers.sqlite3,
requests the source site, or exports original pricing and private records.
"""
from collections import Counter, defaultdict
import hashlib
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse

from gift_supplier_registry import PRIVATE_ROOT
from sync_shop_sources import ROOT

PUBLIC = ROOT/'data/gift'
LOCAL_LABELS = {'186':'안전·소방용품','179':'자동차 기타용품','56756':'홍보용 사탕·젤리'}
REPRESENTATIVE = {'1':'타올','6':'볼펜','2':'텀블러','422':'앞치마','5':'벽시계',
    '56522':'골프공','3':'우산','7':'차량','4':'키링','8':'크리스탈','461':'현수막','303':'선물세트'}


def text(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def image_url(value):
    value=text(value)
    parsed=urlparse(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid public gift image')
    return value


def save(path, data):
    content=json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n'
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists() or path.read_text()!=content:path.write_text(content)


def project(db, source_categories):
    roots=[dict(zip(('id','name','complete'),r)) for r in db.execute('SELECT id,name,complete FROM roots ORDER BY rowid')]
    if not roots or not all(r['complete'] for r in roots) or db.execute("SELECT value FROM scan_state WHERE key='final_verified'").fetchone()!=('1',):
        raise ValueError('Gift inventory coverage is not verified')
    names={c['id']:text(c['name']) for c in source_categories}
    names.update({r['id']:r['name'] for r in roots})
    names.update(LOCAL_LABELS)
    raw={pid:json.loads(record) for pid,record in db.execute('SELECT id,record_json FROM products')}
    members=defaultdict(list)
    for rid,pid in db.execute('SELECT root_id,product_id FROM memberships'):
        if rid not in {r['id'] for r in roots} or pid not in raw:raise ValueError('Gift membership is unresolved')
        members[pid].append(rid)
    if set(members)!=set(raw):raise ValueError('Gift products are missing category membership')
    details={pid:json.loads(record) for pid,record in db.execute('SELECT id,record_json FROM public_details')}
    categories={r['id']:{'id':r['id'],'name':text(r['name']),'parent_ids':[],'count':0} for r in roots}
    products=[]; public_details={}; observations=[]
    for pid in sorted(raw,key=int,reverse=True):
        p=raw[pid];d=details.get(pid,{})
        if not re.fullmatch(r'[1-9]\d{0,11}',pid) or p['product_id']!=pid or (d and d.get('product_id')!=pid):
            raise ValueError('Gift product identity mismatch')
        leaf=p['leaf_category_id']
        if leaf not in names:raise ValueError('Gift category needs a reviewed label: '+leaf)
        if leaf not in categories:categories[leaf]={'id':leaf,'name':names[leaf],'parent_ids':[],'count':0}
        for rid in members[pid]:
            if leaf!=rid and rid not in categories[leaf]['parent_ids']:categories[leaf]['parent_ids'].append(rid)
        ids=list(dict.fromkeys([*members[pid],leaf]))
        for cid in ids:categories[cid]['count']+=1
        verified=bool(d.get('detail_complete'))
        photo=image_url((d.get('main_images') or [p['image']])[0])
        record={'id':pid,'name':text(d.get('name') or p['name']),'image':photo,
            'category_ids':ids,'detail_available':verified,'soldout':bool(d.get('soldout'))}
        products.append(record)
        observations.append(p['observed_at'])
        if verified:
            # Explicit public whitelist. No supplier contacts, source prices,
            # credentials, exposure flags or opaque original records.
            choices=[]
            for option in d.get('options',[]):
                choice={k:text(option.get('selection',{}).get(k)) for k in ('color','size','printing')}
                if any(choice.values()) and choice not in choices:choices.append(choice)
            public_details[pid]={'id':pid,
                'images':list(dict.fromkeys(image_url(u) for u in [*d.get('main_images',[]),*d.get('detail_images',[])])),
                'specifications':[{'name':text(s['name']),'value':text(s['value'])} for s in d.get('specifications',[])],
                'minimum_quantity':d.get('minimum_quantity'),'choices':choices}
    for c in categories.values():
        rows=[p for p in products if c['id'] in p['category_ids']]
        keyword=REPRESENTATIVE.get(c['id'],'')
        representative=next((p for p in rows if keyword and keyword in p['name'] and not p['soldout']),
            next((p for p in rows if not p['soldout']),rows[0]))
        c.update(image=representative['image'],product_id=representative['id'])
    catalog={'meta':{'product_count':len(products),'detail_count':len(public_details),
        'category_count':len(categories),'leaf_category_count':sum(bool(c['parent_ids']) for c in categories.values()),
        'inventory_verified':True,'details_complete':len(products)==len(public_details),
        'observed_at':max(observations),'pricing':'quote','automatic_source_refresh':False},
        'categories':list(categories.values()),'products':products}
    digest=hashlib.sha256(json.dumps([catalog,public_details],ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
    catalog['meta']['revision']=digest
    return catalog,public_details


def build():
    source=json.loads((ROOT/'data/catalog/sources/nadaun-gift.json').read_text())
    with sqlite3.connect((PRIVATE_ROOT/'inventory.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        catalog,details=project(db,source['categories'])
    save(PUBLIC/'catalog.json',catalog)
    save(PUBLIC/'manifest.json',{'meta':catalog['meta'],'categories':catalog['categories']})
    buckets={f'{n:02x}':{} for n in range(256)}
    for pid,d in details.items():buckets[f'{int(pid)%256:02x}'][pid]=d
    for key,data in buckets.items():save(PUBLIC/'details'/f'{key}.json',data)
    urls=['https://shop.nadaun.co/gifts.html']+[
        'https://shop.nadaun.co/gifts.html?category='+c['id'] for c in catalog['categories']]+[
        'https://shop.nadaun.co/gift-item.html?id='+p['id'] for p in catalog['products']]
    maps=[]
    for i in range(0,len(urls),40000):
        filename=f'gift-sitemap-{i//40000+1}.xml';maps.append(filename)
        content='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+escape(u)+'</loc></url>' for u in urls[i:i+40000])+'</urlset>\n'
        path=ROOT/filename
        if not path.exists() or path.read_text()!=content:path.write_text(content)
    (ROOT/'gift-sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<sitemap><loc>https://shop.nadaun.co/'+f+'</loc></sitemap>' for f in maps)+'</sitemapindex>\n')
    print(json.dumps(catalog['meta'],ensure_ascii=False),flush=True)
    return catalog


if __name__=='__main__':build()
