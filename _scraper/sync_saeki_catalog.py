"""Read the public brand catalogue at a bounded rate, preserving checkpoints."""
import json,time,re
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse,parse_qs
import requests
from bs4 import BeautifulSoup
from sync_shop_sources import save_json

BASE='https://www.saeki.co.kr'
def now():return datetime.now(timezone.utc).isoformat()
class Source:
 def __init__(self,root,control=None):
  self.root=Path(root);self.control=Path(control) if control else self.root
  self.session=requests.Session();self.session.headers['User-Agent']='NADAUNShopCatalog/1.0 (+https://shop.nadaun.co)';self.last=0
 def request(self,method,path,**kw):
  if any((r/'source-suspended.json').exists() for r in (self.root,self.control)):raise RuntimeError('Source access remains suspended')
  time.sleep(max(0,2.1-(time.monotonic()-self.last)))
  try:r=self.session.request(method,BASE+path,timeout=(10,40),allow_redirects=False,**kw)
  finally:self.last=time.monotonic()
  if r.status_code in (401,403,429) or re.search(r'접근이?\s*(?:금지|차단)|Access Denied|Too Many Requests',r.text,re.I):
   save_json(self.control/'source-suspended.json',{'at':now(),'status':r.status_code,'suspended':True,'automatic_resume':False});raise RuntimeError('Source protection response; collection suspended')
  r.raise_for_status()
  if r.is_redirect:raise ValueError('Unexpected redirect')
  return r
 def brand(self,bid):
  r=self.request('GET','/brand/brandHome',params={'brndId':bid});d=BeautifulSoup(r.text,'lxml')
  token=d.select_one('meta[name="X-CSRF-TOKEN"]');form=d.select_one('#majorForm')
  if not token or not form:
   # The menu's Z CAM landing page is a public soft-404. Its normal public
   # brand-search endpoint still returns brand 104 with matching identities.
   if bid=='104' and '해당 페이지를 찾을 수 없습니다' in d.get_text():
    fields,token=self.brand('1');fields['brndIdList']=bid
    save_json(self.root/'brand-104-landing-status.json',{'observed_at':now(),'status':'public_landing_page_missing','search':'public_brand_filter','brand_id':bid})
    return fields,token
   raise ValueError('Brand search form absent')
  fields={x['name']:x.get('value','') for x in form.select('input[name]')}
  if fields.get('brndIdList')!=bid:raise ValueError('Wrong brand page')
  fields.update(sorting='new',rowsPerPage='100',_csrf=token['content']);return fields,token['content']
 def page(self,bid,page,fields,token):
  d=self.request('POST','/brand/search-brand-item-list-json',data=fields|{'pageNo':str(page)},headers={'X-CSRF-TOKEN':token,'X-Requested-With':'XMLHttpRequest','Referer':BASE+'/brand/brandHome?brndId='+bid}).json()
  if ('paginationInfo' not in d and d.get('itemList')==[] and page==1
      and d.get('foSearchCriteria',{}).get('brndIdList')==[bid]):
   # The storefront explicitly returns [] without pagination for empty brands.
   d['empty_result_without_pagination']=True
   d['paginationInfo']={'currentPageNo':1,'recordCountPerPage':100,'totalRecordCount':0,'totalPageCount':0}
  if 'paginationInfo' not in d:
   save_json(self.root/f'parse-errors/{bid}-{page}.json',d)
   raise ValueError('Brand pagination absent; response saved for review')
  pg=d['paginationInfo'];items=d['itemList'];total=pg['totalRecordCount']
  if pg['currentPageNo']!=page or pg['recordCountPerPage']!=100:raise ValueError('Wrong brand pagination')
  if len(items)!=min(100,max(0,total-(page-1)*100)):raise ValueError('Incomplete brand page')
  if len({x['itemId'] for x in items})!=len(items):raise ValueError('Duplicate page identity')
  for p in items:
   if str(p['brndId'])!=bid or not re.fullmatch(r'PD\d+',p['itemId']) or not p['itemNm'] or not p['brndNm']:raise ValueError('Unresolved item identity or brand')
  return d

def collect_inventory(root,control=None):
 ROOT=Path(root);ROOT.mkdir(parents=True,exist_ok=True)
 def save(name,data):save_json(ROOT/name,data)
 source=Source(ROOT,control);html=source.request('GET','/brand/main').text;doc=BeautifulSoup(html,'lxml');brands={}
 for a in doc.select('a[href*="/brand/brandHome?brndId="]'):
  bid=parse_qs(urlparse(a['href']).query)['brndId'][0];name=a.get_text(' ',strip=True)
  if bid.isdigit() and name:brands[bid]={'id':bid,'name':name,'url':BASE+a['href']}
 if len(brands)<50:raise ValueError('Brand menu incomplete')
 save('brands.json',{'observed_at':now(),'brands':list(brands.values())})
 allproducts={};coverage=[]
 for i,(bid,brand) in enumerate(brands.items(),1):
  done=ROOT/'brands'/f'{bid}.json'
  if done.exists():record=json.loads(done.read_text())
  else:
   fields,token=source.brand(bid);first=source.page(bid,1,fields,token);total=first['paginationInfo']['totalRecordCount'];pages=max(1,first['paginationInfo']['totalPageCount']);items={}
   for page in range(1,pages+1):
    f=ROOT/'pages'/f'{bid}-{page}.json'
    data=first if page==1 else json.loads(f.read_text()) if f.exists() else source.page(bid,page,fields,token)
    if data['paginationInfo']['totalRecordCount']!=total:raise ValueError('Brand total changed; review saved generation')
    save(f.relative_to(ROOT),data)
    for p in data['itemList']:
     if p['itemId'] in items:raise ValueError('Repeated product across brand pages')
     items[p['itemId']]=p
   if len(items)!=total:raise ValueError('Brand coverage incomplete')
   check=source.page(bid,1,fields,token)
   if check['paginationInfo']['totalRecordCount']!=total or [p['itemId'] for p in check['itemList']]!=[p['itemId'] for p in first['itemList']]:raise ValueError('Brand first page changed')
   record={'brand':brand,'total':total,'verified_at':now(),'products':items};save(done.relative_to(ROOT),record)
  for pid,p in record['products'].items():
   if pid in allproducts and allproducts[pid]!=p:raise ValueError('Conflicting brand identity')
   allproducts[pid]=p
  coverage.append({'brand_id':bid,'expected':record['total'],'unique':len(record['products']),'verified_at':record['verified_at']})
  save('progress.json',{'at':now(),'phase':'inventory','brands_total':len(brands),'brands_complete':i,'products_found':len(allproducts),'published':False})
  print('brand',i,'/',len(brands),brand['name'],record['total'],'total',len(allproducts),flush=True)
 menu=BeautifulSoup(source.request('GET','/brand/main').text,'lxml')
 current={parse_qs(urlparse(a['href']).query)['brndId'][0] for a in menu.select('a[href*="/brand/brandHome?brndId="]') if a.get_text(' ',strip=True)}
 if current!=set(brands):raise ValueError('Brand menu changed during collection')
 save('inventory.json',{'source':'saeki','collected_at':now(),'complete':True,'brands':list(brands.values()),'coverage':coverage,'products':allproducts,'product_count':len(allproducts)})
 save('progress.json',{'at':now(),'phase':'inventory_complete','brands_total':len(brands),'brands_complete':len(brands),'products_found':len(allproducts),'details_complete':False,'published':False})
 return json.loads((ROOT/'inventory.json').read_text())


def collect_details(root,control=None,batch_size=100):
 """One bounded, resumable batch. Failed details never become verified records."""
 import gzip,hashlib
 from itertools import zip_longest
 from saeki_detail_parser import parse_detail
 root=Path(root);source=Source(root,control)
 inventory=json.loads((root/'inventory.json').read_text())
 if not inventory.get('complete'):raise ValueError('Complete inventory required')
 groups={b['id']:[]for b in inventory['brands']}
 for p in inventory['products'].values():groups[str(p['brndId'])].append(p)
 products=[p for row in zip_longest(*groups.values())for p in row if p]
 revision=hashlib.sha256(Path(__file__).with_name('saeki_detail_parser.py').read_bytes()).hexdigest()
 errors={};processed=0
 holds=json.loads((root/'reviewed-content-holds.json').read_text())if(root/'reviewed-content-holds.json').exists()else{}
 index_path=root/'detail-index.json'
 index=json.loads(index_path.read_text())if index_path.exists()else{}
 verified_ids=set(index.get('verified_ids',[]))if index.get('parser_revision')==revision else set()
 existing={f.stem:f for f in (root/'details').glob('*.json')}
 if not index or index.get('parser_revision')!=revision:
  for path in existing.values():
   row=json.loads(path.read_text())
   if row.get('parser_revision')==revision:verified_ids.add(row['id'])
 verified_ids.difference_update(holds)
 old_errors=json.loads((root/'detail-errors.json').read_text())if(root/'detail-errors.json').exists()else{}
 (root/'html').mkdir(exist_ok=True);(root/'details').mkdir(exist_ok=True)
 for p in products:
  pid=p['itemId'];raw=root/'html'/(pid+'.html.gz');parsed=root/'details'/(pid+'.json')
  if 'saeki-'+pid in verified_ids or 'saeki-'+pid in holds:continue
  if old_errors.get(pid,{}).get('parser_revision')==revision:continue
  if processed>=batch_size:continue
  checked_at=now()
  try:
   if raw.exists():
    body=gzip.decompress(raw.read_bytes()).decode();checked_at=datetime.fromtimestamp(raw.stat().st_mtime,timezone.utc).isoformat()
   elif (root/('detail-'+pid+'.html')).exists():
    sample=root/('detail-'+pid+'.html');body=sample.read_text();checked_at=datetime.fromtimestamp(sample.stat().st_mtime,timezone.utc).isoformat()
   else:
    body=source.request('GET','/item/itemDetail',params={'itemId':pid}).text
    raw.write_bytes(gzip.compress(body.encode(),mtime=0))
   result=parse_detail(body,p,checked_at);result['parser_revision']=revision
   save_json(parsed,result);verified_ids.add(result['id'])
  except ValueError as exc:errors[pid]={'name':p['itemNm'],'error':str(exc),'parser_revision':revision}
  processed+=1
  if processed%10==0:
   save_json(root/'detail-progress.json',{'at':now(),'phase':'details','total':len(products),'verified':len(verified_ids),'errors':len(errors),'published':False})
 old_errors.update(errors)
 for pid in list(old_errors):
  if 'saeki-'+pid in verified_ids or 'saeki-'+pid in holds:del old_errors[pid]
 save_json(root/'detail-errors.json',old_errors)
 progress={'at':now(),'phase':'details','total':len(products),'verified':len(verified_ids),'errors':len(old_errors),'content_held':len(holds),'details_complete':len(verified_ids)==len(products),'complete':len(verified_ids)+len(holds)==len(products),'processed_this_batch':processed,'published':False,'parser_revision':revision}
 save_json(index_path,{'parser_revision':revision,'verified_ids':sorted(verified_ids)})
 save_json(root/'detail-progress.json',progress)
 if progress['complete']:
  verified={pid:json.loads((root/'details'/(pid.removeprefix('saeki-')+'.json')).read_text())for pid in verified_ids}
  from saeki_publication import prepare
  candidate=prepare(inventory,verified,holds)
  save_json(root/'catalogue-candidate.json',candidate)
 return progress
