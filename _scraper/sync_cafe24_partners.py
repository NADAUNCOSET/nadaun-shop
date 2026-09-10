"""Guarded, resumable public catalogue reads for the three Cafe24 partners.

Each generation must cover the advertised brand-root inventory and every
descendant category. Partial data stays private; access denials never retry.
"""
from copy import deepcopy
import argparse
import ast
import gzip
import hashlib
import json
import math
import re
import sqlite3
import time
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
import requests
from sync_shop_sources import ROOT, clean, save_json, stamp
from sync_gift_inventory import run_lock

SITES={
    'clmedia':('https://clmedia.co.kr','24'),
    'cinemall':('https://www.cinemall.co.kr','56'),
    'onnoff':('https://onnoff.kr','23'),
}
STATE=ROOT/'_scraper/.sync-state'


def category_id(url):
    m=re.search(r'/category/[^/]+/(\d+)/?',url)
    return parse_qs(urlparse(url).query).get('cate_no',[m[1] if m else None])[0]


def product_id(url):
    m=re.search(r'/product/[^/]+/(\d+)/?',url)
    return parse_qs(urlparse(url).query).get('product_no',[m[1] if m else None])[0]


def soup(body):
    return BeautifulSoup(body,'lxml')


def category_menu(doc,parent):
    rows={}
    for menu in doc.select('.menuCategory'):
        for a in menu.select('a[href]'):
            cid=category_id(a['href'])
            if cid and cid!=parent:
                # Nested HTML menus contain grandchildren. Their enclosing
                # category LI supplies the parent instead of flattening them.
                ancestors=list(a.parents);li=next((n for n in ancestors if n.name=='li'),None)
                outer=next((n for n in li.parents if n.name=='li'),None) if li else None
                outer_link=outer.find('a') if outer else None
                pid=category_id(outer_link.get('href','')) if outer_link else parent
                name=re.sub(r'\s*\([\d,]*\)\s*$','',a.get_text(' ',strip=True)).strip()
                if name:rows[cid]={'id':cid,'name':name,'parent_id':pid or parent}
    return list(rows.values())


def category_tree(payload,root):
    if not isinstance(payload,list) or not payload:raise ValueError('Category API returned no tree')
    nodes={str(x['cate_no']):{'id':str(x['cate_no']),'name':clean(soup(x['name']).get_text()),
        'parent_id':str(x['parent_cate_no'])} for x in payload}
    if root not in nodes:raise ValueError('Brand root absent from category API')
    result={root:{**nodes[root],'parent_id':None}}
    for cid,node in nodes.items():
        current=cid;seen=set()
        while current in nodes and current!=root:
            if current in seen:raise ValueError('Category cycle')
            seen.add(current);current=nodes[current]['parent_id']
        if current==root:result[cid]={**node,'parent_id':None if cid==root else node['parent_id']}
    return result


def listing(doc,source,cid,page):
    base,_=SITES[source];counter=doc.select_one('.prdCount')
    match=re.search(r'[\d,]+',counter.get_text() if counter else '')
    if not match:raise ValueError('Missing advertised category total: '+cid)
    total=int(match[0].replace(',',''));products={}
    for li in doc.select('.xans-product-listnormal li[id^="anchorBoxId_"]'):
        sid=li['id'].split('_')[-1];a=next((a for a in li.select('a[href]') if product_id(a['href'])==sid),None)
        name=li.select_one('.name');im=li.select_one('img[id^="eListPrdImage"]')
        if not a or not name or not im:raise ValueError('Incomplete listing identity: '+sid)
        label=re.sub(r'^상품명\s*:?\s*','',name.get_text(' ',strip=True)).strip()
        if not label or '\ufffd' in label:raise ValueError('Invalid product name encoding')
        if sid in products:raise ValueError('Duplicate ID within category page')
        products[sid]={'id':source+'-'+sid,'source':source,'source_id':sid,
            'source_url':base+'/product/detail.html?product_no='+sid,'name':label,
            'images':{'thumb':urljoin(base,im.get('src',''))},'listing_checked_at':stamp()}
    last=max([page,*[int(parse_qs(urlparse(a['href']).query).get('page',['1'])[0])
                    for a in doc.select('.xans-product-normalpaging a[href]')]])
    active=doc.select_one('.xans-product-normalpaging .this')
    if active and active.get_text(strip=True)!=str(page):raise ValueError('Wrong category page returned')
    if total and not products:raise ValueError('Empty nonempty category page')
    if page==1 and products:last=max(last,math.ceil(total/len(products)))
    return {'products':products,'total':total,'last':last,'children':category_menu(doc,cid)}


def js_values(doc):
    text='\n'.join(s.get_text() for s in doc.select('script:not([src])'))
    literal=r"(?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|true|false|null|-?\d+(?:\.\d+)?)"
    result={}
    for name,raw in re.findall(r'\bvar\s+(\w+)\s*=\s*('+literal+r')\s*;',text):
        if raw in ('true','false','null'):value=json.loads(raw)
        else:
            try:value=ast.literal_eval(raw)
            except (ValueError,SyntaxError):continue
        result[name]=value
    return result


def detail(doc,product,brand):
    p=deepcopy(product);base,_=SITES[p['source']];sid=p['source_id'];schema=None
    for script in doc.select('script[type="application/ld+json"]'):
        try:obj=json.loads(script.get_text(),strict=False)
        except ValueError:continue
        rows=obj if isinstance(obj,list) else obj.get('@graph',[obj])
        schema=next((x for x in rows if x.get('@type')=='Product'),schema)
    if not schema:raise ValueError('Product schema absent')
    if '\ufffd' in schema.get('name',''):raise ValueError('Invalid detail name encoding')
    offer=schema.get('offers') or {}
    if not isinstance(offer,dict) or product_id(offer.get('url',''))!=sid:raise ValueError('Detail identity mismatch')
    if offer.get('priceCurrency')!='KRW':raise ValueError('Expected KRW price')
    raw=offer.get('price')
    if not re.fullmatch(r'\d+(?:\.0+)?',str(raw)):raise ValueError('Unverified price')
    price=int(float(raw));values=js_values(doc)
    script_price=values.get('product_price')
    if script_price is not None and str(price)!=str(script_price):raise ValueError('Schema and displayed price differ')
    sale_node=doc.select_one('#span_product_price_sale')
    sale=price
    if sale_node:
        n=re.search(r'\d[\d,]*',sale_node.get_text())
        if n:sale=int(n[0].replace(',',''))
    images=schema.get('image') or []
    if isinstance(images,str):images=[images]
    images=list(dict.fromkeys(urljoin(base,i) for i in images if isinstance(i,str)))
    if not images or any(urlparse(u).scheme not in ('https','http') for u in images):raise ValueError('Main product images missing')
    body=doc.select_one('#prdDetail .cont, #prdDetailContent, #prdDetail')
    descriptions=[]
    if body:
        for i in body.select('img'):
            value=i.get('ec-data-src') or i.get('data-src') or i.get('src') or ''
            if value and not value.startswith('data:'):descriptions.append(urljoin(base,value))
    groups=[]
    for node in doc.select('select[option_select_element], select[id^="product_option_id"]'):
        vals=[{'value':o.get('value'),'label':o.get_text(' ',strip=True)} for o in node.select('option') if o.get('value') not in ('','*','**',None)]
        groups.append({'name':node.get('option_title') or node.get('option_name') or node.get('name'),'values':vals})
    stock_raw=values.get('single_option_stock_data');stock=json.loads(stock_raw) if isinstance(stock_raw,str) and stock_raw else None
    supplier='unknown';issues=[]
    if stock:
        supplier='soldout' if stock.get('use_stock') and stock.get('use_soldout')=='T' and int(stock.get('stock_number',0))<=0 else 'available'
    elif values.get('option_stock_data'):
        try:stock=json.loads(values['option_stock_data'])
        except (ValueError,TypeError):issues.append('option_stock_requires_review')
    option_raw=values.get('option_stock_data')
    if groups or (isinstance(stock,dict) and not stock_raw):issues.append('option_combinations_require_review')
    if supplier=='unknown':issues.append('availability_requires_review')
    if not body or not (descriptions or body.get_text(' ',strip=True)):issues.append('description_missing')
    if not brand:issues.append('brand_membership_requires_review')
    p.update(name=clean(schema['name']),brand=brand or '미분류',kind='purchase',price=price,sale_price=sale,
        status='soldout' if supplier=='soldout' else 'inquiry',supplier_status=supplier,
        images={'thumb':images[0],'main':images,'detail':list(dict.fromkeys(descriptions))},
        description_text=body.get_text(' ',strip=True) if body else clean(schema.get('description','')),
        option_groups=groups,options=[],options_require_confirmation=bool(groups or option_raw),
        detail_status='verified' if not issues else 'review_required',content_issues=issues,
        detail_checked_at=stamp())
    # Preserve the source's option/stock evidence privately, never in public JSON.
    return p,{'schema':schema,'option_stock':stock,'option_type':values.get('option_type'),
              'item_code':values.get('item_code'),'selling_price_content':values.get('product_price_content')}


class Source:
    def __init__(self,source,work,interval=5):
        self.source=source;self.work=work;self.base=SITES[source][0];self.next=0;self.interval=interval
        self.session=requests.Session();self.session.headers['User-Agent']='NADAUNShopCatalog/1.0 (+https://shop.nadaun.co)'

    def get(self,path,**params):
        latch=self.work/'source-suspended.json'
        if latch.exists() and json.loads(latch.read_text()).get('suspended',True):raise RuntimeError('Provider access suspended; manual review required')
        time.sleep(max(0,self.next-time.monotonic()))
        try:r=self.session.get(self.base+path,params=params,timeout=(10,40),allow_redirects=False)
        finally:self.next=time.monotonic()+self.interval
        if r.status_code in (403,429) or re.search(r'접근\s*금지|차단된\s*(?:IP|아이피)|비정상적인 접근|서버보호차원',r.text,re.I):
            save_json(latch,{'suspended':True,'at':stamp(),'http_status':r.status_code,'automatic_resume':False})
            raise RuntimeError('Provider protection response; requests stopped')
        if r.status_code!=200:raise RuntimeError('Source HTTP '+str(r.status_code))
        return r.content


class Collector:
    def __init__(self,source):
        self.name=source;self.base,self.root=SITES[source];self.work=STATE/source;self.work.mkdir(exist_ok=True,parents=True)
        self.source=Source(source,self.work);self.db=sqlite3.connect(self.work/'checkpoint.sqlite3',timeout=30)
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS pages(category TEXT,page INTEGER,record TEXT NOT NULL,PRIMARY KEY(category,page));
          CREATE TABLE IF NOT EXISTS details(id TEXT PRIMARY KEY,record TEXT NOT NULL,evidence TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS errors(id TEXT PRIMARY KEY,error TEXT NOT NULL,at TEXT NOT NULL);
        ''')

    def state(self,key,value=None):
        if value is not None:
            with self.db:self.db.execute('INSERT OR REPLACE INTO state VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
            return value
        row=self.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None

    def page(self,cid,page,fresh=False):
        row=None if fresh else self.db.execute('SELECT record FROM pages WHERE category=? AND page=?',(cid,page)).fetchone()
        if row:return json.loads(row[0])
        raw=self.source.get('/product/list.html',cate_no=cid,page=page)
        value=listing(soup(raw),self.name,cid,page)
        if not fresh:
            with self.db:self.db.execute('INSERT INTO pages VALUES(?,?,?)',(cid,page,json.dumps(value,ensure_ascii=False)))
        return value

    def inventory(self):
        nodes=self.state('categories')
        if nodes is None:
            raw=self.source.get('/exec/front/Product/SubCategory');payload=json.loads(raw)
            if payload:nodes=category_tree(payload,self.root)
            else:nodes={self.root:{'id':self.root,'name':'브랜드','parent_id':None}}
            self.state('categories',nodes)
        products={};memberships={};coverage=[];checked=set();queue=list(nodes)
        for cid in queue:
            p=1;end=1;found={};total=None
            while p<=end:
                if p>1000:raise RuntimeError('Unexpected pagination depth')
                row=self.page(cid,p)
                if total is None:total=row['total']
                if total!=row['total']:raise ValueError('Source total changed mid-category')
                if set(found)&set(row['products']):raise ValueError('Repeated product across pages')
                found.update(row['products']);end=max(end,row['last'])
                for child in row['children']:
                    if child['id'] not in nodes:
                        nodes[child['id']]=child;queue.append(child['id'])
                save_json(self.work/'progress.json',{'at':stamp(),'phase':'inventory','category_id':cid,
                    'page':p,'pages_in_category':end,'categories_verified':len(checked),'categories_found':len(nodes),
                    'products_found':len(set(products)|set(found)),'complete':False})
                p+=1
            if len(found)!=total:raise ValueError('Category unique count differs from source total: '+cid)
            products.update(found)
            for sid in found:memberships.setdefault(sid,[]).append(cid)
            coverage.append({'id':cid,'expected':total,'unique':len(found),'pages':end})
            checked.add(cid);self.state('categories',nodes)
            save_json(self.work/'progress.json',{'at':stamp(),'phase':'inventory','categories_verified':len(checked),'categories_found':len(nodes),'products_found':len(products),'complete':False})
        root_all={sid for sid,cats in memberships.items() if self.root in cats}
        extra=set(products)-root_all
        if extra:raise ValueError('Brand root does not cover all descendants: '+str(len(extra)))
        roots={cid:node for cid,node in nodes.items() if node['parent_id']==self.root}
        for sid,product in products.items():
            labels=set();cats=memberships[sid]
            for cid in cats:
                cursor=cid;seen=set()
                while cursor not in roots and cursor!=self.root:
                    if cursor in seen or cursor not in nodes:raise ValueError('Invalid category ancestry')
                    seen.add(cursor);cursor=nodes[cursor]['parent_id']
                if cursor in roots:labels.add(roots[cursor]['name'])
            product['brand']=next(iter(labels)) if len(labels)==1 else ''
            product['brand_category_ids']=[cid for cid in cats if cid!=self.root]
        result={'source':self.name,'at':stamp(),'categories':list(nodes.values()),'coverage':coverage,'products':products,'product_count':len(products),'inventory_complete':True,'complete':False}
        save_json(self.work/'inventory-candidate.json',result)
        self.state('inventory_complete',True)
        return result

    def collect(self):
        with run_lock(self.work):
            snapshot=self.inventory()
            for sid,p in snapshot['products'].items():
                if self.db.execute('SELECT 1 FROM details WHERE id=? UNION SELECT 1 FROM errors WHERE id=?',(sid,sid)).fetchone():continue
                raw=self.source.get('/product/detail.html',product_no=sid)
                try:record,evidence=detail(soup(raw),p,p['brand'])
                except (ValueError,KeyError,TypeError) as exc:
                    with self.db:self.db.execute('INSERT OR REPLACE INTO errors VALUES(?,?,?)',(sid,str(exc),stamp()))
                    folder=self.work/'review-pages';folder.mkdir(exist_ok=True)
                    (folder/(sid+'.html.gz')).write_bytes(gzip.compress(raw))
                else:
                    evidence['html_sha256']=hashlib.sha256(raw).hexdigest()
                    with self.db:self.db.execute('INSERT INTO details VALUES(?,?,?)',(sid,json.dumps(record,ensure_ascii=False),json.dumps(evidence,ensure_ascii=False)))
                    if record['content_issues']:
                        folder=self.work/'review-pages';folder.mkdir(exist_ok=True)
                        (folder/(sid+'.html.gz')).write_bytes(gzip.compress(raw))
                counts=self.db.execute('SELECT (SELECT COUNT(*) FROM details),(SELECT COUNT(*) FROM errors)').fetchone()
                save_json(self.work/'progress.json',{'at':stamp(),'phase':'details','products_found':len(snapshot['products']),'details_checked':sum(counts),'details_parsed':counts[0],'detail_errors':counts[1],'complete':False})
            changed=[]
            for category in snapshot['coverage']:
                old=self.page(category['id'],1);new=self.page(category['id'],1,True)
                if old['total']!=new['total'] or list(old['products'])!=list(new['products']):changed.append(category['id'])
            rows={sid:json.loads(rec) for sid,rec in self.db.execute('SELECT id,record FROM details')}
            errors=dict(self.db.execute('SELECT id,error FROM errors'))
            reviews={sid:p.get('content_issues',[]) for sid,p in rows.items() if p['detail_status']!='verified'}
            result={**snapshot,'collected_at':stamp(),'products':{p['id']:p for p in rows.values()},'product_count':len(rows),
                'complete':not errors and not reviews and not changed and len(rows)==snapshot['product_count'],
                'detail_errors':errors,'content_reviews':reviews,'changed_categories':changed}
            save_json(self.work/'catalogue-candidate.json',result)
            save_json(self.work/'progress.json',{'at':stamp(),'phase':'review_required' if not result['complete'] else 'ready_for_source_selection',
                'products_found':snapshot['product_count'],'details_parsed':len(rows),'details_verified':len(rows)-len(reviews),
                'detail_errors':len(errors),'content_reviews':len(reviews),'changed_categories':changed,'complete':result['complete'],'published':False})
            return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',choices=SITES);args=parser.parse_args()
    collector=Collector(args.source)
    try:
        error=collector.work/'worker-error.json'
        if error.exists() and json.loads(error.read_text()).get('requires_review'):return
        if (collector.work/'catalogue-candidate.json').exists():return
        collector.collect()
    except Exception as exc:
        save_json(collector.work/'worker-error.json',{'at':stamp(),'error':type(exc).__name__+': '+str(exc),'requires_review':True});raise
    finally:collector.db.close()


if __name__=='__main__':main()
