"""Owner-approved20 brand roots from observed Sunphoto public navigation."""
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urljoin,urlsplit,parse_qs
import gzip,hashlib,json,math,re,unicodedata
from bs4 import BeautifulSoup
import sync_cafe24_partners as cafe

BASE='https://sunphoto.kr';ROOTS={'29': 'TAMRON', '30': 'Voigtlander', '28': 'BOYA', '25': 'Kenko', '24': 'Kenko Telescopes', '156': 'COLBOR', '84': 'SLIK', '85': 'HEIPI', '86': 'WEIFENG', '26': 'DOMKE', '27': 'COTTON', '81': 'JOBY', '82': 'Kodak & Polaroid', '83': 'Sunwayfoto', '87': 'CELESTRON', '625': 'SKYWATCHER', '88': 'MEADE', '89': 'NATIONAL GEOGRAPHIC', '256': 'NASA', '578': 'DWARF LAB'}
# The public menu is a product group; schema and visible brand both say Kenko.
GROUP_MANUFACTURERS={'Kenko Telescopes':'Kenko'}
GROUP_ALLOWED={'Kodak & Polaroid':('Kodak & Polaroid','Kodak','Polaroid')}
MANUFACTURER_REVIEWS={
 '2063':{'group':'Kenko Telescopes','brand':'onetoten','expected_name':'onetoten 8x22 쌍안경 Yellow'},
 '1048':{'group':'Kodak & Polaroid','brand':'ZINK','expected_name':'징크 Zink 정품 SNAP/Mint 전용 Zink Paper 2X3" (스티커 타입) 20매'},
 '1517':{'group':'Sunwayfoto','brand':'썬포토','visible_brand':'자체브랜드','expected_name':'26650 Li-ion Battery for FL-152'}
}
def manufacturer_key(value):return ''.join(c for c in unicodedata.normalize('NFKC',str(value)).casefold() if c.isalnum())
def stamp():return datetime.now(timezone.utc).isoformat()
def clean(s):return re.sub(r'\s+',' ',str(s or '')).strip()
def save(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,separators=(',',':'))+'\n')
def document(b):return BeautifulSoup(b,'lxml')
def sid(url):
    parsed=urlsplit(url);query=parse_qs(parsed.query).get('product_no',[''])[0]
    if query:return query
    m=re.search(r'/product/[^/]+/(\d+)(?:/|$)',parsed.path);return m[1] if m else ''

def reviewed_detail(raw,product,brand):
    groups=[brand] if isinstance(brand,str) else sorted(brand)
    allowed={manufacturer_key(value):value for group in groups for value in GROUP_ALLOWED.get(group,(GROUP_MANUFACTURERS.get(group,group),))}
    page=document(raw)
    for image in page.select('#prdDetailContent img'):
        value=image.get('ec-data-src') or image.get('data-src') or image.get('src','')
        if value.startswith('data:image/'):
            from inline_product_images import materialize
            image['ec-data-src']=materialize(value,'sunphoto')
    record,evidence=cafe.detail(page,product,groups[0],source_base=BASE)
    actual=evidence['schema'].get('brand',{})
    actual=actual.get('name','') if isinstance(actual,dict) else str(actual)
    review=MANUFACTURER_REVIEWS.get(str(product.get('source_id')))
    if review and review['group'] in groups and record['name']==review['expected_name']:
        allowed[manufacturer_key(review['brand'])]=review['brand']
    if manufacturer_key(actual) not in allowed:raise ValueError('Sunphoto schema manufacturer differs from selected scope')
    if len(groups)>1 or actual.casefold()!=groups[0].casefold():
        visible=[clean(i.select_one('dd').get_text()) for i in page.select('.detail-spec__item')
                 if i.select_one('dt') and i.select_one('dd') and clean(i.select_one('dt').get_text())=='브랜드']
        visible_expected=review.get('visible_brand',actual) if review and review['group'] in groups and record['name']==review['expected_name'] else actual
        if visible!=[visible_expected]:raise ValueError('Sunphoto grouped manufacturer requires visible/schema agreement')
        record.update(source_brand_group=groups[0] if len(groups)==1 else None,source_brand_groups=groups)
        if visible_expected=='자체브랜드':record['description_notice']='공급처가 자체브랜드로 표시한 배터리입니다. 호환 모델과 배터리 규격을 확인해주세요.'
    record.update(brand=allowed[manufacturer_key(actual)],source_declared_brand=actual)
    if record.get('content_issues')==['description_missing']:
        body=page.select_one('#prdDetailContent')
        facts=[]
        for item in page.select('.detail-spec__item'):
            key,value=item.select_one('dt'),item.select_one('dd')
            if key and value and clean(key.get_text()) in ('상품명','브랜드','원산지'):
                facts.append(clean(key.get_text())+': '+clean(value.get_text(' ',strip=True)))
        if body is not None and not body.get_text(strip=True) and not body.select('img') and len(facts)==3:
            record.update(description_text='\n'.join(facts),description_notice='공급처에 상세 설명이 등록되지 않은 상품입니다. 세부 사양과 호환성은 문의해주세요.',
                description_text_alongside_images=True,source_description_empty=True,detail_status='verified',content_issues=[])
    if record.get('detail_status')!='verified':raise ValueError('Sunphoto content requires review: '+','.join(record.get('content_issues',[])))
    record.update(evidence_sha256=hashlib.sha256(raw).hexdigest(),observed_at=stamp())
    return record

def listing(page,cid):
    n=page.select_one('.list-total-count__count')
    if n is None or not re.fullmatch(r'[\d,]+',n.get_text(strip=True)):raise ValueError('Sunphoto advertised count missing')
    total=int(n.get_text(strip=True).replace(',',''));rows={}
    for li in page.select('.xans-product-listnormal .product-list__item'):
        a=li.select_one('.product-box__link[href]');im=li.select_one('.product-box__img[src]')
        if not a or not im:raise ValueError('Sunphoto product card identity absent')
        number=sid(a['href']);name=clean(im.get('alt'))
        if not number.isdigit() or not name or number in rows:raise ValueError('Sunphoto invalid/duplicate product')
        thumb=urljoin(BASE,im['src'])
        rows[number]={'id':'sunphoto-'+number,'source':'sunphoto','source_id':number,'name':name,
                      'source_url':urljoin(BASE,a['href']),'images':{'thumb':thumb}}
    if total and not rows or len(rows)>total:raise ValueError('Sunphoto count/card mismatch')
    return total,rows

class Source:
    def __init__(self,work):self.work=work;self.client=cafe.Source('sunphoto',work,interval=5,base=BASE)
    def get(self,path,fresh=False,**params):
        if urlsplit(urljoin(BASE,path)).hostname!='sunphoto.kr':raise ValueError('Unexpected Sunphoto source host')
        key=hashlib.sha256(json.dumps([path,params],sort_keys=True).encode()).hexdigest();p=self.work/'responses'/(key+'.html.gz')
        if (self.work/'source-suspended.json').exists():raise RuntimeError('Sunphoto source reads suspended')
        if p.exists() and not fresh:return gzip.decompress(p.read_bytes())
        raw=self.client.get(path,**params);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(gzip.compress(raw));return raw

def collect(work):
    work=Path(work);work.mkdir(parents=True,exist_ok=True);source=Source(work)
    payload=json.loads(source.get('/exec/front/Product/SubCategory'));allnodes={str(n['cate_no']):n for n in payload}
    nodes={}
    for cid,n in allnodes.items():
        cursor=cid;seen=set()
        while cursor in allnodes and cursor not in seen:
            seen.add(cursor)
            if cursor in ROOTS:
                nodes[cid]={'id':cid,'name':n['name'],'brand':ROOTS[cursor],'parent_id':str(n['parent_cate_no']) if str(n['parent_cate_no'])!= '1' else None};break
            cursor=str(allnodes[cursor]['parent_cate_no'])
    if set(ROOTS)-nodes.keys():raise ValueError('Sunphoto selected brand navigation missing')
    for cid,label in ROOTS.items():
        if nodes[cid]['name'].casefold()!=label.casefold():raise ValueError('Sunphoto owner-scoped brand root changed')
    rows={};memberships={};coverage=[];first_pages={}
    for cid,n in nodes.items():
        first=document(source.get('/product/list.html',cate_no=cid,sort_method='5',page=1));total,products=listing(first,cid);first_pages[cid]=(total,list(products))
        pages=max(1,math.ceil(total/max(1,len(products))));items={}
        for page in range(1,pages+1):
            current,batch=(total,products) if page==1 else listing(document(source.get('/product/list.html',cate_no=cid,sort_method='5',page=page)),cid)
            if current!=total or set(items)&set(batch):raise ValueError('Sunphoto source changed/duplicates across pages')
            items.update(batch)
        if len(items)!=total:raise ValueError('Sunphoto complete category coverage mismatch')
        for number,p in items.items():
            if number in rows and rows[number]['name']!=p['name']:raise ValueError('Sunphoto source product identity changed')
            rows.setdefault(number,p);memberships.setdefault(number,set()).add(cid)
        coverage.append({'id':cid,'expected':total,'unique':len(items)})
        save(work/'progress.json',{'at':stamp(),'phase':'inventory','categories_checked':len(coverage),'categories_total':len(nodes),'products_found':len(rows),'published':False})
        print(json.dumps({'phase':'inventory','category':cid,'total':total,'products_found':len(rows)}),flush=True)
    products={};errors={};details=work/'details';details.mkdir(exist_ok=True)
    for number,p in rows.items():
        brands={nodes[cid]['brand'] for cid in memberships[number]}
        if not brands:raise ValueError('Sunphoto product has no approved source group')
        brand=next(iter(brands)) if len(brands)==1 else sorted(brands);file=details/(number+'.json')
        try:
            if file.exists():record=json.loads(file.read_text())
            else:
                p.update(brand=brand,brand_category_ids=sorted(memberships[number]),kind='purchase')
                u=urlsplit(p['source_url']);raw=source.get(u.path,**{k:v[0] for k,v in parse_qs(u.query).items()})
                record=reviewed_detail(raw,p,brand);save(file,record)
            record['brand_category_ids']=sorted(memberships[number]);products[record['id']]=record
        except (ValueError,KeyError) as exc:errors[number]=str(exc)
        if (len(products)+len(errors))%10==0:
            save(work/'progress.json',{'at':stamp(),'phase':'details','products_found':len(rows),'details_verified':len(products),'errors':errors,'published':False})
            print(json.dumps({'phase':'details','verified':len(products),'errors':len(errors)}),flush=True)
    for cid,(total,first_ids) in first_pages.items():
        current,batch=listing(document(source.get('/product/list.html',fresh=True,cate_no=cid,sort_method='5',page=1)),cid)
        if current!=total or list(batch)!=first_ids:raise ValueError('Sunphoto final category reconciliation changed')
    result={'source':'sunphoto','source_url':BASE,'collected_at':stamp(),'complete':not errors,'product_count':len(products),'products':products,
            'categories':list(nodes.values()),'coverage':coverage,'detail_errors':errors,'owner_brand_roots':ROOTS,'snapshot_kind':'owner_scoped_full_source'}
    save(work/'catalogue-candidate.json',result);return result

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser();a.add_argument('--work',type=Path,required=True);args=a.parse_args();collect(args.work)
