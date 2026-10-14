"""Resume the complete brand catalogue; publish only reconciled verified details."""
import argparse,hashlib,json,os,plistlib,shutil,socket,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from contextlib import contextmanager
from sync_shop_sources import ROOT,OUT,save_json,stamp
from sync_saeki_catalog import collect_inventory,collect_details
from saeki_publication import validate_candidate

STATE=ROOT/'_scraper/.sync-state/saeki'
DATA=ROOT/'_private/catalog'

def read(path):return json.loads(path.read_text())if path.exists()else{}
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def revision():return hashlib.sha256(b''.join((ROOT/'_scraper'/f).read_bytes()for f in ('sync_saeki_catalog.py','saeki_detail_parser.py','saeki_publication.py','saeki_categories.py','saeki_worker.py'))).hexdigest()

@contextmanager
def lock():
 STATE.mkdir(parents=True,exist_ok=True);path=STATE/'worker.lock'
 if path.exists():
  owner=read(path)
  if owner.get('host')!=socket.gethostname():raise BlockingIOError('Worker owned by another host')
  try:os.kill(owner['pid'],0)
  except ProcessLookupError:path.unlink()
  else:raise BlockingIOError('Saeki worker already active')
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
 with os.fdopen(fd,'w')as f:json.dump({'host':socket.gethostname(),'pid':os.getpid(),'at':stamp()},f)
 try:yield
 finally:path.unlink(missing_ok=True)


def publish(candidate):
 from brand_source_policy import supplemental_source_approved,publishable_ids,policy_fingerprint
 from shop_sync import run,request,SITE
 validate_candidate(candidate)
 if not supplemental_source_approved('saeki'):raise ValueError('Saeki owner approval missing')
 previous=read(STATE/'published.json')
 if candidate['product_count']<previous.get('source_verified_products',0)*.85:raise ValueError('Saeki inventory decreased more than 15 percent')
 result=run(existing=True,source_updates={'saeki':candidate})
 live=request('GET',SITE+'/data/catalog/catalog.json',params={'verify':result['revision']}).json()
 if read(OUT/'saeki.json')!=candidate:raise ValueError('Published Saeki source differs from candidate')
 actual={o['id']for p in live['products']for o in p['offers']if o['source']=='saeki'}
 expected=publishable_ids(candidate)
 if actual!=expected:raise ValueError('Live Saeki offers differ from verified source')
 receipt={**result,'source_verified_products':candidate['product_count'],'live_products':len(actual),'verified_products':len(actual),'scope':'all_shop_brands',
  'source_sha256':hashlib.sha256((OUT/'saeki.json').read_bytes()).hexdigest(),
  'excluded_ids':sorted(set(candidate['products'])-expected),
  'excluded_by_source':candidate['publication']['excluded'],'excluded_by_existing_owner_policy':sorted(set(candidate['products'])-expected),
  'candidate_sha256':digest(candidate),'policy_sha256':policy_fingerprint()}
 save_json(STATE/'published.json',receipt)
 save_json(STATE/'progress.json',{'at':stamp(),'phase':'live_verified','complete':True,'published':True,'live_products':len(actual),'revision':result['revision']})
 return receipt


def work():
 with lock():
  if (STATE/'source-suspended.json').exists():return {'phase':'source_suspended','requests':0}
  fingerprint=revision();error=read(STATE/'worker-error.json')
  if error.get('requires_review')and error.get('parser_revision')==fingerprint:return {'phase':'error_requires_review','requests':0}
  generation=read(STATE/'generation.json')
  if not generation:
   folder=DATA/('saeki-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'));folder.mkdir(parents=True)
   generation={'directory':folder.name,'started_at':stamp()};save_json(STATE/'generation.json',generation)
  folder=DATA/generation['directory']
  if folder.parent!=DATA or not folder.name.startswith('saeki-'):raise ValueError('Invalid Saeki generation path')
  # Never overlap the initial verified private collector during migration.
  initial_lock=read(folder/'details.lock')
  if initial_lock:
   if initial_lock.get('host')!=socket.gethostname():raise BlockingIOError('Initial collector is active on another host')
   try:os.kill(initial_lock['pid'],0)
   except ProcessLookupError:pass
   else:raise BlockingIOError('Initial detail collector is active')
  candidate=read(folder/'catalogue-candidate.json');receipt=read(STATE/'published.json')
  if candidate.get('complete') and (candidate.get('parser_revision')!=hashlib.sha256((ROOT/'_scraper/saeki_detail_parser.py').read_bytes()).hexdigest() or candidate.get('brand_classification_revision')!=hashlib.sha256((ROOT/'_scraper/saeki_publication.py').read_bytes()).hexdigest()):candidate={}
  if candidate.get('complete'):
   from brand_source_policy import policy_fingerprint
   if receipt.get('candidate_sha256')!=digest(candidate)or receipt.get('policy_sha256')!=policy_fingerprint():return publish(candidate)
   age=(datetime.now(timezone.utc)-datetime.fromisoformat(receipt['verified_at'])).total_seconds()
   if age<43200:return {'phase':'current','next_refresh_seconds':int(43200-age)}
   folder=DATA/('saeki-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'));folder.mkdir()
   save_json(STATE/'generation.json',{'directory':folder.name,'started_at':stamp()})
  if not read(folder/'inventory.json').get('complete'):collect_inventory(folder,STATE)
  while True:
   if revision()!=fingerprint:return {'phase':'code_changed_resume_on_next_tick'}
   progress=collect_details(folder,STATE,batch_size=100)
   save_json(STATE/'progress.json',{**progress,'generation':folder.name})
   print(json.dumps(progress,ensure_ascii=False),flush=True)
   if progress['complete']:return publish(read(folder/'catalogue-candidate.json'))
   if not progress['processed_this_batch']:
    raise ValueError('Saeki detail errors require review; verified content preserved')


def install():
 label='co.nadaun.shop.saeki-sync';target=f'gui/{os.getuid()}/{label}'
 if subprocess.run(['launchctl','print',target],capture_output=True).returncode==0:raise RuntimeError('Saeki worker already installed; preserve active process')
 logs=Path.home()/'Library/Logs/NADAUN/shop';logs.mkdir(parents=True,exist_ok=True)
 path=Path.home()/'Library/LaunchAgents'/(label+'.plist');path.parent.mkdir(parents=True,exist_ok=True)
 entry="import runpy,sys;sys.path.insert(0,"+repr(str(ROOT/'_scraper'))+");runpy.run_module('saeki_worker',run_name='__main__')"
 definition={'Label':label,'ProgramArguments':['/usr/bin/caffeinate','-i',sys.executable,'-c',entry],
  'WorkingDirectory':str(Path.home()),'RunAtLoad':True,'StartInterval':600,'ProcessType':'Standard',
  'StandardOutPath':str(logs/'saeki.stdout.log'),'StandardErrorPath':str(logs/'saeki.stderr.log'),
  'EnvironmentVariables':{'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTHONUNBUFFERED':'1'}}
 if path.exists():raise RuntimeError('Existing Saeki schedule needs review')
 with path.open('wb')as f:plistlib.dump(definition,f)
 subprocess.run(['launchctl','enable',target],check=True)
 subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(path)],check=True)
 loaded=subprocess.check_output(['launchctl','print',target],text=True)
 if 'saeki_worker'not in loaded:raise RuntimeError('Saeki NAS worker did not load')
 save_json(STATE/'schedule.json',{'installed_at':stamp(),'label':label,'loaded':True,'refresh_interval_seconds':43200,'resume_interval_seconds':600,'request_interval_seconds':2.1,'source_script':'_scraper/saeki_worker.py','requires':'Mac awake, NAS mounted, network available'})

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--install',action='store_true');args=parser.parse_args()
 if args.install:install()
 else:
  try:
   result=work();print(json.dumps(result,ensure_ascii=False),flush=True)
  except BlockingIOError as exc:print(str(exc),flush=True)
  except Exception as exc:
   from cafe24_worker import retryable_error
   save_json(STATE/'worker-error.json',{'at':stamp(),'error':type(exc).__name__+': '+str(exc),'requires_review':not retryable_error(exc),'parser_revision':revision(),'published':False})
   raise
