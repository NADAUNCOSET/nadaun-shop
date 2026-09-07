"""Read public gift details and quantity pricing without executing source scripts.

Factory data and our eventual selling prices are not part of this projection.
Only the supported public price formula is recognized; samples and quantities
below the advertised minimum require a separate quote.
"""
from collections import defaultdict
from decimal import Decimal, ROUND_CEILING
import json
import re
from urllib.parse import urljoin, urlparse, parse_qs
from sync_gift_inventory import BASE, Source, Inventory, run_lock, stamp


def parse_detail(doc, pid):
    products=[]
    for script in doc.select('script[type="application/ld+json"]'):
        try:parsed=json.loads(script.get_text())
        except ValueError:continue
        candidates=parsed if isinstance(parsed,list) else parsed.get('@graph',[parsed])
        products += [x for x in candidates if isinstance(x,dict) and x.get('@type')=='Product']
    schema=next((x for x in products if str(x.get('sku'))==str(pid)),None)
    visible=doc.select_one('#goods_name')
    if schema is None or visible is None:raise ValueError('Gift detail identity is not verified')
    if '\ufffd' in visible.get_text():raise ValueError('Gift product name has invalid encoding')
    offer=schema.get('offers') or {}
    if isinstance(offer,list):offer=offer[0] if offer else {}
    status=str(offer.get('availability','')).rsplit('/',1)[-1]
    text='\n'.join(s.get_text() for s in doc.select('script:not([type="application/ld+json"])'))
    arrays={name:{} for name in ('color','size','matierial','quantity','atprice')}
    literal=r'"(?:[^"\\]|\\.)*"'
    for match in re.finditer(r'(?m)^\s*(color|size|matierial|quantity|atprice)\[(\d+)\]\s*=\s*('+literal+r')\s*;',text):
        name,index,value=match[1],int(match[2]),json.loads(match[3],strict=False)
        if index in arrays[name]:raise ValueError('Gift option index is repeated')
        arrays[name][index]=value
    minimum=re.search(r'\bvar\s+minquantity\s*=\s*(\d+)\s*;',text)
    rate=re.search(r'\bvar\s+discountrate\s*=\s*(\d+(?:\.\d+)?)\s*;',text)
    function=re.search(r'function\s+atpriceToint\s*\([^)]*\)\s*\{([^}]+)\}',text)
    formula=re.search(r'Math\.ceil\(\s*atprice\s*\*\s*(\d+(?:\.\d+)?)\s*\)',function[1] if function else '')
    quantity=arrays['quantity'];prices=arrays['atprice']
    if not minimum or not rate or not formula or Decimal(rate[1])!=Decimal(formula[1]):
        raise ValueError('Gift public price formula needs review')
    discount=Decimal(rate[1])
    if not 0<discount<=1 or int(minimum[1])<1 or not quantity or set(quantity)!=set(prices):
        raise ValueError('Gift quantity-price table is incomplete')
    indices=set(quantity)
    if any(a and set(a)!=indices for k,a in arrays.items() if k not in ('quantity','atprice')):
        raise ValueError('Gift option dimensions are incomplete')
    groups=defaultdict(list)
    for index in sorted(indices):
        if not quantity[index].isdigit() or not prices[index].isdigit():raise ValueError('Gift tier is not a positive integer')
        qty,raw=int(quantity[index]),int(prices[index])
        if qty<1 or raw<1:raise ValueError('Gift tier amount requires review')
        key=tuple(arrays[n].get(index,'') for n in ('color','size','matierial'))
        groups[key].append({'minimum_quantity':qty,'unit_price_ex_vat':int((Decimal(raw)*discount).to_integral_value(rounding=ROUND_CEILING))})
    options=[]
    for key,tiers in groups.items():
        tiers.sort(key=lambda row:row['minimum_quantity'])
        if len({x['minimum_quantity'] for x in tiers})!=len(tiers):raise ValueError('Gift quantity thresholds conflict')
        options.append({'selection':dict(zip(('color','size','printing'),key)),'tiers':tiers})
    body=doc.select_one('.detail_bimg')
    main=doc.select_one('.magnified-image[src]')
    if body is None or main is None:raise ValueError('Gift product image regions are missing')
    def image_url(value):
        u=urljoin(BASE,value)
        if urlparse(u).scheme not in ('http','https'):raise ValueError('Gift image URL is invalid')
        return u
    images=list(dict.fromkeys(image_url(i['src']) for i in body.select('img[src]') if '/DATA/EVENT/' not in i['src']))
    specifications=[]
    for th in body.select('.gdet_table th'):
        td=th.find_next_sibling('td')
        if td:specifications.append({'name':th.get_text(' ',strip=True),'value':td.get_text(' ',strip=True)})
    exposure=re.search(r'\bvar\s+is_outpotal\s*=\s*"([YN])"',text)
    return {'product_id':str(pid),'name':visible.get_text(' ',strip=True),
            'source_url':BASE+'/new/shop/detail.php?code='+str(pid),
            'main_images':[image_url(main['src'])],'detail_images':images,'specifications':specifications,
            'supplier_availability':status or 'unknown','soldout':status in ('OutOfStock','SoldOut','Discontinued'),
            'minimum_quantity':int(minimum[1]),'options':options,'vat_rate':'0.1',
            'external_display_allowed':exposure[1]=='Y' if exposure else None,
            'sample_quote_required':True,'below_minimum_quote_required':True,
            'observed_at':stamp(),'detail_complete':True,'supplier_complete':False,'selling_price_approved':False}


def collect_details(root=None, batch=1000):
    inventory=Inventory(root) if root is not None else Inventory()
    try:
        if not inventory.status()['inventory_complete']:raise ValueError('Complete gift inventory is required before detail reconciliation')
        with run_lock(inventory.root):
            db=inventory.db
            db.executescript('''
                CREATE TABLE IF NOT EXISTS public_details(id TEXT PRIMARY KEY, record_json TEXT NOT NULL, observed_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS detail_errors(id TEXT PRIMARY KEY, error TEXT NOT NULL, checked_at TEXT NOT NULL);
            ''')
            source=Source(inventory.root)
            # Invalid pages remain explicit review items; they never stop the
            # remaining inventory from being read or overwrite verified data.
            rows=db.execute('''SELECT p.id FROM products p LEFT JOIN public_details d ON p.id=d.id
                LEFT JOIN detail_errors e ON p.id=e.id WHERE d.id IS NULL AND e.id IS NULL ORDER BY p.rowid LIMIT ?''',(batch,)).fetchall()
            for (pid,) in rows:
                doc=source.get(BASE+'/new/shop/detail.php',code=pid)
                try:product=parse_detail(doc,pid)
                except ValueError as exc:
                    with db:db.execute('INSERT INTO detail_errors VALUES(?,?,?)',(pid,str(exc),stamp()))
                else:
                    with db:db.execute('INSERT INTO public_details VALUES(?,?,?)',(pid,json.dumps(product,ensure_ascii=False),product['observed_at']))
            status=detail_status(inventory)
            (inventory.root/'details-progress.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps(status,ensure_ascii=False),flush=True)
            return status
    finally:inventory.db.close()


def detail_status(inventory):
    db=inventory.db
    total=db.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    verified=db.execute('SELECT COUNT(*) FROM public_details').fetchone()[0]
    errors=db.execute('SELECT COUNT(*) FROM detail_errors').fetchone()[0]
    return {'checked_at':stamp(),'products':total,'details_verified':verified,'needs_review':errors,
            'details_remaining':total-verified-errors,'details_complete':total==verified and total>0,
            'suppliers_complete':False,'published':False}


if __name__=='__main__':collect_details()
