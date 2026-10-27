"""Public DigitalCP inventory with explicit brand exclusions and saved evidence.

Reads only the category/list/detail links exposed by the storefront. Never
executes source scripts, changes supplier data, or publishes partial results.
"""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import gzip, hashlib, json, math, re, time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
import requests
from bs4 import BeautifulSoup

BASE='https://www.digitalcp.co.kr'
EXCLUDED={'nisi','니시','smallrig','스몰리그','dji','gopro','고프로'}
EXCLUDED_CODES={'041':'NiSi','028':'SmallRig','023':'DJI','040':'GoPro'}
PARSER_REVISION=3
class OwnerExcluded(ValueError):pass
def stamp():return datetime.now(timezone.utc).isoformat()
def clean(value):return re.sub(r'\s+',' ',str(value or '')).strip()
def normalized(value):return re.sub(r'[^a-z0-9가-힣]','',clean(value).casefold())
def excluded(brand):return normalized(brand) in EXCLUDED
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n')
def doc(body):return BeautifulSoup(body,'lxml')
def amount(value):
    s=re.sub(r'[,\s원]','',str(value))
    if not re.fullmatch(r'-?\d+(?:\.0+)?',s):raise ValueError('Unverified DigitalCP won amount')
    return int(Decimal(s))
def number_url(url,key):return parse_qs(urlsplit(url).query).get(key,[''])[0]
def media(value):
    url=urljoin(BASE,value)
    if urlsplit(url).scheme not in ('http','https') or not urlsplit(url).hostname:raise ValueError('Unsafe DigitalCP media URL')
    return url

def navigation(page):
    result={}
    for a in page.select('a[href*="cateCd="]'):
        url=urljoin(BASE+'/goods/goods_list.php',a['href']);cid=number_url(url,'cateCd')
        if urlsplit(url).hostname!='www.digitalcp.co.kr' or not re.fullmatch(r'(?:\d{3})+',cid):continue
        name=re.sub(r'\s*\(\s*[\d,]+\s*\)\s*$','',clean(a.get_text(' ',strip=True)))
        if name and not name.isdigit():result.setdefault(cid,{'id':cid,'name':name,'parent_id':cid[:-3] or None})
    return result

def listing(page,cid):
    counter=page.select_one('.pick_list_num strong')
    if counter is None:raise ValueError('DigitalCP inventory count missing: '+cid)
    total=amount(counter.get_text());products={}
    for node in page.select('.goods_list .item_cont'):
        a=node.select_one('.item_tit_box a[href*="goods_view.php?goodsNo="]')
        name=node.select_one('.item_name');image=node.select_one('.item_photo_box img[src]')
        if not a or not name or not image:raise ValueError('DigitalCP product card identity missing')
        sid=number_url(a['href'],'goodsNo')
        if not re.fullmatch(r'[1-9]\d{0,11}',sid) or sid in products:raise ValueError('DigitalCP duplicate/invalid product identity')
        brand=node.select_one('.item_brand');price=node.select_one('.item_price')
        fixed=node.select_one('.fixed-price');price_text=clean(price.get_text()) if price else ''
        sold=bool(node.select_one('.item_soldout,.icon_soldout,.soldout')) or '품절' in price_text
        inquiry='문의' in price_text
        sale=amount(price_text) if price and not inquiry and not sold and re.search(r'\d',price_text) else None
        regular=amount(fixed.get_text()) if fixed else sale
        products[sid]={'source_id':sid,'name':clean(name.get_text()),'brand':clean(brand.get_text()) if brand else '',
                       'price':regular,'sale_price':sale,'listed_soldout':sold,'listed_inquiry':inquiry,'image':media(image['src'])}
    if total and not products or len(products)>total:raise ValueError('DigitalCP count/card mismatch')
    return total,products

def parse_detail(body,sid,listed):
    page=doc(body);form=page.select_one('#frmView');title=page.select_one('.item_detail_tit h3')
    if not form or not title:raise ValueError('DigitalCP product detail identity missing')
    identity=page.select_one('meta[property="og:url"]')
    if identity and number_url(identity.get('content',''),'goodsNo')!=sid:raise ValueError('DigitalCP detail URL identity mismatch')
    if clean(title.get_text())!=listed['name']:raise ValueError('DigitalCP listing/detail title changed')
    fields={}
    for n in form.select('input[name]'):
        if n.get('value','') and not fields.get(n['name']):fields[n['name']]=n['value']
    if fields.get('brandCd') in EXCLUDED_CODES:raise OwnerExcluded(EXCLUDED_CODES[fields['brandCd']])
    if not fields.get('set_goods_price'):raise ValueError('DigitalCP detail price missing')
    sale=amount(fields['set_goods_price']);regular=amount(fields.get('set_goods_fixedPrice') or sale)
    if regular==0:regular=sale
    if listed['sale_price'] is not None and sale!=listed['sale_price']:raise ValueError('DigitalCP listing/detail price changed')
    if regular<0 or sale<0:raise ValueError('DigitalCP price range needs review')
    specs=[];brand=''
    for dl in page.select('.item_detail_list dl'):
        dt,dd=dl.find('dt'),dl.find('dd')
        if not dt or not dd:continue
        k,v=clean(dt.get_text()),clean(dd.get_text(' ',strip=True))
        if k=='브랜드':brand=v
        if k in ['브랜드','원산지','제품구성','추천조합','세트총무게','제조사']:specs.append({'name':k,'value':v})
    if not brand:brand=listed['brand'] or '브랜드 미표기'
    if listed['brand'] and normalized(brand)!=normalized(listed['brand']):raise ValueError('DigitalCP brand mismatch')
    if excluded(brand):raise OwnerExcluded(brand)
    gallery=list(dict.fromkeys(media(n['src']) for n in page.select('.item_photo_big img[src]') if not re.search(r'/icon/|icon_zoom',n['src'])))
    source_image_missing=False
    if not gallery:
        if urlsplit(listed['image']).path.endswith('/data/commonimg/ico_noimg_500.gif'):
            gallery=[listed['image']];source_image_missing=True
        else:raise ValueError('DigitalCP original gallery missing')
    region=page.select_one('#detail .txt-manual')
    if region is None:raise ValueError('DigitalCP detail content region missing')
    for n in region.select('script,style,iframe,form'):n.decompose()
    def detail_image(value):
        if value.startswith('data:image/'):
            from inline_product_images import materialize
            return materialize(value,'digitalcp')
        return media(value)
    images=list(dict.fromkeys(detail_image(n['src']) for n in region.select('img[src]')))
    options=[];groups=[];unknown=False
    for select in form.select('select[name^="optionSnoInput"],select[name^="optionNo"]'):
        values=[]
        for node in select.select('option[value]'):
            raw=node['value']
            if not raw:continue
            parts=raw.split('^|^');cells=parts[0].split('||')
            if len(parts)<2 or len(cells)<2 or not re.fullmatch(r'-?\d+(?:\.0+)?',cells[1]):unknown=True;continue
            delta=amount(cells[1]);label=clean(parts[1])
            if not cells[0].isdigit() or not label or sale+delta<0:raise ValueError('DigitalCP option identity/price needs review')
            option={'id':cells[0],'name':label,'additional_price':delta,'price':sale+delta,'soldout':node.has_attr('disabled') or '품절' in node.get_text()}
            options.append(option);values.append({'value':raw,'text':clean(node.get_text())})
        if values:groups.append({'name':select.get('name','옵션'),'values':values})
    if len(groups)>1:options=[];unknown=True
    if fields.get('optionFl')=='y' and not groups:unknown=True
    sold=listed['listed_soldout'] or bool(form.select_one('.btn_add_soldout,.btn_soldout'))
    cid=fields.get('cateCd','')
    if cid and not re.fullmatch(r'(?:\d{3})+',cid):raise ValueError('DigitalCP native product category malformed')
    public_price=listed['sale_price'] is not None
    if not public_price:
        for option in options:option.update(price=None,additional_price=0)
        unknown=bool(options) or unknown
    return {'id':'digitalcp-'+sid,'source':'digitalcp','source_id':sid,'source_url':BASE+'/goods/goods_view.php?goodsNo='+sid,
            'kind':'purchase','name':listed['name'],'brand':brand,'price':regular or None if public_price else None,'sale_price':sale or None if public_price else None,
            'status':'soldout' if sold else 'sale' if sale and public_price else 'inquiry','supplier_status':'soldout' if sold else 'listed',
            'images':{'thumb':listed['image'],'main':gallery,'detail':images},'description_text':'\n'.join(x['name']+': '+x['value'] for x in specs),
            'specifications':specs,'options':options,'option_groups':groups,'options_require_confirmation':unknown,
            'detail_status':'verified','native_category_id':cid,'source_brand_code':fields.get('brandCd',''),
            'source_image_missing':source_image_missing,'description_notice':'공급처에서도 상품 이미지를 준비 중입니다. 제품 구성과 호환성은 문의해주세요.' if source_image_missing else '',
            'source_reference_price_below_selling':regular<sale,
            'parser_revision':PARSER_REVISION,'evidence_sha256':hashlib.sha256(body).hexdigest(),'observed_at':stamp()}

class Source:
    def __init__(self,work,interval=2.1):
        self.work=Path(work);self.work.mkdir(parents=True,exist_ok=True);self.next=0;self.interval=max(2.1,interval)
        self.session=requests.Session();self.session.headers['User-Agent']='NADAUNShopCatalog/1.0 (+https://shop.nadaun.co)'
    def get(self,path,params=None,fresh=False):
        if (self.work/'source-suspended.json').exists():raise RuntimeError('DigitalCP source remains suspended')
        url=urljoin(BASE,path)
        if urlsplit(url).hostname!='www.digitalcp.co.kr':raise ValueError('Unexpected DigitalCP source host')
        key=hashlib.sha256(json.dumps([url,params],sort_keys=True).encode()).hexdigest();cache=self.work/'responses'/(key+'.html.gz')
        if cache.exists() and not fresh:return gzip.decompress(cache.read_bytes())
        time.sleep(max(0,self.next-time.monotonic()))
        try:r=self.session.get(url,params=params,timeout=(10,40),allow_redirects=False)
        finally:self.next=time.monotonic()+self.interval
        if r.status_code in (401,403,429) or re.search(r'Access Denied|접근이?\s*금지|차단된\s*(IP|아이피)|서버보호차원',r.text,re.I):
            save(self.work/'source-suspended.json',{'at':stamp(),'http_status':r.status_code,'automatic_resume':False});raise RuntimeError('DigitalCP protection response; source reads stopped')
        if r.status_code!=200:raise RuntimeError('DigitalCP source HTTP '+str(r.status_code))
        cache.parent.mkdir(exist_ok=True);cache.write_bytes(gzip.compress(r.content));return r.content

def collect(work):
    work=Path(work);source=Source(work);initial=doc(source.get('/goods/goods_list.php',{'cateCd':'023'}));nodes=navigation(initial)
    roots=[cid for cid in nodes if len(cid)==3 and cid!='038']
    if '023' not in roots or len(roots)<8:raise ValueError('DigitalCP main navigation incomplete')
    inventory={};memberships={};coverage=[];first_pages={}
    for cid in roots:
        first=doc(source.get('/goods/goods_list.php',{'cateCd':cid,'pageNum':40,'page':1}));nodes.update(navigation(first));total,items=listing(first,cid);first_pages[cid]=(total,items)
        expected_pages=max(1,math.ceil(total/40));all_items={}
        for number in range(1,expected_pages+1):
            current,rows=(total,items) if number==1 else listing(doc(source.get('/goods/goods_list.php',{'cateCd':cid,'pageNum':40,'page':number})),cid)
            if current!=total or set(all_items)&set(rows):raise ValueError('DigitalCP list changed/duplicated during pagination')
            all_items.update(rows)
        if len(all_items)!=total:raise ValueError('DigitalCP complete category coverage mismatch: '+cid)
        for sid,p in all_items.items():
            if sid in inventory and inventory[sid]!=p:raise ValueError('DigitalCP identity/price differs across source categories')
            inventory[sid]=p;memberships.setdefault(sid,[]).append(cid)
        coverage.append({'id':cid,'expected':total,'unique':len(all_items)})
        save(work/'progress.json',{'at':stamp(),'phase':'inventory','categories_checked':len(coverage),'products_found':len(inventory),'published':False})
        print(json.dumps({'phase':'inventory','category':cid,'total':total,'unique_products':len(inventory)}),flush=True)
    save(work/'inventory.json',{'observed_at':stamp(),'products':inventory,'memberships':memberships,'categories':nodes,'coverage':coverage,'complete':True})
    products={};excluded_counts=Counter();errors={};categories={};detail_dir=work/'details';detail_dir.mkdir(exist_ok=True)
    for index,(sid,listed) in enumerate(inventory.items(),1):
        if excluded(listed['brand']):excluded_counts[listed['brand']]+=1;continue
        path=detail_dir/(sid+'.json')
        try:
            if path.exists() and json.loads(path.read_text()).get('parser_revision')==PARSER_REVISION:p=json.loads(path.read_text())
            else:
                p=parse_detail(source.get('/goods/goods_view.php',{'goodsNo':sid}),sid,listed);save(path,p)
            branch=set(memberships[sid]);native=p['native_category_id']
            native_path=[native[:length] for length in range(3,len(native)+1,3)]
            if native_path and all(cid in nodes for cid in native_path):branch.update(native_path)
            elif native:p['native_category_label_requires_review']=native
            brandkey=normalized(p['brand'])
            for cid in sorted(branch,key=lambda x:(len(x),x)):
                if cid not in nodes:raise ValueError('DigitalCP native category label is not observed: '+cid)
                k=brandkey+':'+cid;parent=brandkey+':'+cid[:-3] if cid[:-3] in branch else None
                categories[k]={'id':k,'name':nodes[cid]['name'],'brand':p['brand'],'parent_id':parent}
            p['brand_category_ids']=[brandkey+':'+cid for cid in sorted(branch)];products[p['id']]=p
        except OwnerExcluded as exc:excluded_counts[str(exc)]+=1
        except (ValueError,KeyError) as exc:errors[sid]=str(exc)
        if index%10==0 or index==len(inventory):
            save(work/'progress.json',{'at':stamp(),'phase':'details','products_found':len(inventory),'details_verified':len(products),'excluded':sum(excluded_counts.values()),'errors':errors,'published':False})
            print(json.dumps({'phase':'details','verified':len(products),'excluded':sum(excluded_counts.values()),'errors':len(errors)}),flush=True)
    if len(products)+sum(excluded_counts.values())+len(errors)!=len(inventory):raise ValueError('DigitalCP source scope partition differs')
    for cid,(total,items) in first_pages.items():
        current,rows=listing(doc(source.get('/goods/goods_list.php',{'cateCd':cid,'pageNum':40,'page':1},fresh=True)),cid)
        if current!=total or rows!=items:raise ValueError('DigitalCP final inventory reconciliation changed: '+cid)
    result={'source':'digitalcp','source_url':BASE,'collected_at':stamp(),'complete':not errors,'product_count':len(products),'products':products,
            'categories':list(categories.values()),'coverage':coverage,'owner_excluded_brands':sorted(EXCLUDED),'excluded_counts':dict(excluded_counts),
            'detail_errors':errors,'source_inventory_count':len(inventory),'snapshot_kind':'owner_scoped_full_source','publication_requires_review':True}
    save(work/'catalogue-candidate.json',result);print(json.dumps({'phase':'complete' if not errors else 'requires_review','products':len(products),'errors':len(errors)}),flush=True)
    return result

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser();a.add_argument('--work',type=Path,required=True);args=a.parse_args();collect(args.work)
