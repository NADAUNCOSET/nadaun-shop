"""Project the saved public gift inventory into an internal shop directory.

Reads inventory.sqlite3 in read-only mode. Never opens suppliers.sqlite3,
requests the source site, or exports private supplier records.
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
from gift_pricing_projection import pricing

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


def project(db, source_categories, include_pricing=False, reviewed_details=()):
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
    for d in reviewed_details:
        if d['product_id'] not in raw:raise ValueError('Reviewed detail is missing inventory identity')
        details[d['product_id']]=d
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
            'category_ids':ids,'detail_available':verified,'soldout':bool(d.get('soldout')) if verified else None}
        products.append(record)
        observations.append(p['observed_at'])
        if verified:
            # Explicit public whitelist. No supplier contacts, private costs,
            # credentials, exposure flags or opaque original records.
            choices=[]
            for option in d.get('options',[]):
                choice={k:text(option.get('selection',{}).get(k)) for k in ('color','size','printing')}
                if any(choice.values()) and choice not in choices:choices.append(choice)
            public_details[pid]={'id':pid,
                'images':list(dict.fromkeys(image_url(u) for u in [*d.get('main_images',[]),*d.get('detail_images',[])])),
                'specifications':[{'name':text(s['name']),'value':text(s['value'])} for s in d.get('specifications',[])],
                'minimum_quantity':d.get('minimum_quantity'),'choices':choices}
            if include_pricing:
                price=pricing(d)
                if price:
                    public_details[pid]['pricing']=price
                    record['pricing_available']=True
                    record['pricing_observed_at']=price['observed_at']
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
        catalog,details=project(db,source['categories'],include_pricing=True,reviewed_details=json.loads((PRIVATE_ROOT/'commerce-integration-20261022/verified-public-details.json').read_text()))
    merge_official_feed(catalog)
    catalog['meta']['priced_product_count']=sum(bool(d.get('pricing')) for d in details.values())
    catalog['meta']['price_option_count']=sum(len(d.get('pricing',{}).get('options',[])) for d in details.values())
    catalog['meta']['price_tier_count']=sum(len(o['tiers']) for d in details.values() for o in d.get('pricing',{}).get('options',[]))
    catalog['meta']['revision']=hashlib.sha256(json.dumps([catalog,details],ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
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


def merge_official_feed(catalog):
    """Union owner-provided IDs. Feed omission never deletes historical products.

    price_pc may represent a set, so it is intentionally not a unit price.
    Unknown labels remain visible under a clearly named source-feed group.
    """
    folder=PRIVATE_ROOT/'full-acquisition-20261021'
    feed=folder/'official-feed-products.jsonl'
    if not feed.exists():raise ValueError('Validated owner feed is required')
    receipt=json.loads((folder/'feed-validation.json').read_text())
    rows=[json.loads(line) for line in feed.read_text().splitlines() if line.strip()]
    if len(rows)!=receipt['validated_rows'] or len({r['id'] for r in rows})!=len(rows):raise ValueError('Feed count mismatch')
    products={p['id']:p for p in catalog['products']}
    cats={c['id']:c for c in catalog['categories']}
    labels=defaultdict(list)
    for c in cats.values():labels[text(c['name'])].append(c['id'])
    aliases={'텀블러':'56521','수건':'282','칼라스티커':'56889'}
    new_count=0
    for row in rows:
        pid=row['id']; label=text(row['category_name1'])
        if pid not in products:
            matches=labels.get(label,[])
            cid=matches[0] if len(matches)==1 else aliases.get(label)
            if cid not in cats:
                rid='feed';cid='feed-'+hashlib.sha256(label.encode()).hexdigest()[:12]
                cats.setdefault(rid,{'id':rid,'name':'본사 제공 상품','parent_ids':[],'count':0})
                cats.setdefault(cid,{'id':cid,'name':label or '분류 확인 중','parent_ids':[rid],'count':0})
            products[pid]={'id':pid,'name':text(row['title']),'image':image_url(row['image_link']),
                'category_ids':list(dict.fromkeys([*cats[cid]['parent_ids'],cid])),
                'detail_available':False,'soldout':None}
            new_count+=1
        p=products[pid]
        p.update(manufacturer_label=text(row['maker']),origin=text(row['origin']),
            feed_category=label,feed_observed_at=receipt['parsed_at'])
    catalog['products']=sorted(products.values(),key=lambda p:int(p['id']),reverse=True)
    for c in cats.values():
        members=[p for p in products.values() if c['id'] in p['category_ids']]
        c['count']=len(members)
        if not c.get('image') and members:c.update(image=members[0]['image'],product_id=members[0]['id'])
    catalog['categories']=list(cats.values())
    catalog['meta'].update(product_count=len(products),category_count=len(cats),
        leaf_category_count=sum(bool(c['parent_ids']) for c in cats.values()),
        official_feed_count=len(rows),official_feed_added=new_count,official_feed_observed_at=receipt['parsed_at'],
        official_feed_sha256=receipt['source_sha256'],all_current_details_verified=False,
        pricing='quantity-estimate-then-confirm')


if __name__=='__main__':build()
