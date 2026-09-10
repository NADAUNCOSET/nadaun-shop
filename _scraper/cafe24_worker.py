"""Collect, reconcile, publish and refresh the three approved Cafe24 partners."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

from cafe24_publication import prepare, digest
from sync_cafe24_partners import Collector, SITES, STATE, run_lock
from sync_shop_sources import ROOT, OUT, stamp, save_json


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def parser_revision():
    return hashlib.sha256(b''.join((ROOT/'_scraper'/name).read_bytes() for name in
        ('sync_cafe24_partners.py','review_cafe24_checkpoint.py'))).hexdigest()


def publish(snapshot):
    from brand_source_policy import supplemental_source_approved, publishable_ids, policy_fingerprint
    from shop_sync import run, request, SITE
    source = snapshot['source']
    if not supplemental_source_approved(source):
        raise RuntimeError('Partner source approval is missing')
    candidate = prepare(snapshot)
    prior = read(STATE/source/'published.json')
    if candidate['product_count'] < prior.get('source_verified_products',0) * .85:
        raise RuntimeError('Partner inventory decreased more than 15%; review before publication')
    result = run(existing=True, source_updates={source:candidate})
    live = request('GET',SITE+'/data/catalog/catalog.json',params={'verify':result['revision']}).json()
    actual = {offer['id'] for product in live['products'] for offer in product['offers'] if offer['source']==source}
    expected = publishable_ids(candidate)
    if actual != expected:
        raise RuntimeError('Partner live product IDs differ from the approved source')
    receipt = {**result,'source':source,'scope':'all','source_collected_at':snapshot['collected_at'],
               'source_verified_products':snapshot['product_count'],'verified_products':len(actual),
               'excluded_ids':sorted(set(candidate['products'])-expected),
               'policy_sha256':policy_fingerprint(),'candidate_sha256':digest(snapshot),
               'source_sha256':hashlib.sha256((OUT/(source+'.json')).read_bytes()).hexdigest()}
    save_json(STATE/source/'published.json',receipt)
    save_json(STATE/source/'progress.json',{'at':stamp(),'phase':'live_verified',
        'products_found':snapshot['product_count'],'details_verified':snapshot['product_count'],
        'complete':True,'published':True,'live_products':len(actual),'revision':result['revision']})
    return receipt


def work(source):
    root = STATE/source
    root.mkdir(parents=True,exist_ok=True)
    control = root/'worker-control'; control.mkdir(exist_ok=True)
    with run_lock(control):
        suspension = read(root/'source-suspended.json')
        if suspension and suspension.get('suspended',True):
            return {'phase':'source_suspended','requests':0}
        fingerprint = parser_revision()
        error = read(root/'worker-error.json')
        if error.get('requires_review') and error.get('parser_revision') == fingerprint:
            return {'phase':'error_requires_review','requests':0}
        generation = read(root/'generation.json')
        folder = root/generation.get('directory','')
        candidate = read(folder/'catalogue-candidate.json')
        receipt = read(root/'published.json')
        from brand_source_policy import policy_fingerprint
        if candidate.get('complete'):
            if (receipt.get('candidate_sha256') != digest(candidate) or
                    receipt.get('policy_sha256') != policy_fingerprint()):
                return publish(candidate)
            age = (datetime.now(timezone.utc)-datetime.fromisoformat(candidate['collected_at'])).total_seconds()
            if age < 12*3600:
                return {'phase':'current','next_refresh_seconds':int(12*3600-age)}
            folder = root/('generation-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
            folder.mkdir()
            save_json(root/'generation.json',{'directory':folder.name,'started_at':stamp()})
            candidate = {}
        marker = read(folder/'parser-review.json')
        if ((folder/'inventory-candidate.json').exists() and
                marker.get('parser_revision') != fingerprint):
            from review_cafe24_checkpoint import review
            result = review(source,apply=True,work=folder)
            save_json(folder/'parser-review.json',{'at':stamp(),'parser_revision':fingerprint,
                'backup':result.get('backup'),'summary':result['summary']})
            candidate = read(folder/'catalogue-candidate.json')
        if candidate and not candidate.get('complete') and not candidate.get('reconciliation_required'):
            return {'phase':'content_review_required','requests':0}
        collector = Collector(source,folder)
        try:
            candidate = collector.collect()
        finally:
            collector.db.close()
        if not candidate['complete']:
            save_json(root/'publication-waiting.json',{'at':stamp(),'state':'content_or_inventory_review',
                'errors':candidate.get('detail_errors'), 'content_reviews':candidate.get('content_reviews'),
                'changed_categories':candidate.get('changed_categories'),'published':False})
            return {'phase':'content_review_required'}
        return publish(candidate)


def install(source):
    """Replace only this source's old collection-only LaunchAgent."""
    label='co.nadaun.shop.'+source+'-sync'; target=f'gui/{os.getuid()}/{label}'
    path=Path.home()/'Library/LaunchAgents'/(label+'.plist')
    previous=read(STATE/source/'schedule.json')
    if subprocess.run(['launchctl','print',target],capture_output=True).returncode==0:
        subprocess.run(['launchctl','bootout',target],check=True)
    logs=Path.home()/'Library/Logs/NADAUN/shop';logs.mkdir(parents=True,exist_ok=True)
    definition={'Label':label,'ProgramArguments':[shutil.which('caffeinate') or '/usr/bin/caffeinate','-i',sys.executable,str(Path(__file__).resolve()),source],
        'WorkingDirectory':str(Path.home()),'RunAtLoad':True,'StartInterval':600,'ProcessType':'Standard',
        'StandardOutPath':str(logs/(source+'.stdout.log')),'StandardErrorPath':str(logs/(source+'.stderr.log')),
        'EnvironmentVariables':{'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTHONUNBUFFERED':'1'}}
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        archive=STATE/source/'schedule-backups';archive.mkdir(exist_ok=True)
        backup=archive/(stamp().replace(':','-')+'.plist')
        backup.write_bytes(path.read_bytes())
    with path.open('wb') as handle:plistlib.dump(definition,handle)
    subprocess.run(['launchctl','enable',target],check=True)
    subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(path)],check=True)
    save_json(STATE/source/'schedule.json',{**previous,'at':stamp(),'label':label,'loaded':True,
        'source_script':'_scraper/cafe24_worker.py','scope':'Full reconciled collection and approved publication',
        'refresh_interval_seconds':43200,'resume_interval_seconds':600,'request_interval_seconds':5})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',choices=SITES)
    parser.add_argument('--install',action='store_true');args=parser.parse_args()
    if args.install:install(args.source)
    else:
        try:
            result=work(args.source)
            error=STATE/args.source/'worker-error.json'
            if result and result.get('phase') not in ('error_requires_review','source_suspended') and error.exists():
                save_json(error,{**read(error),'resolved':True,'requires_review':False,'resolved_at':stamp()})
            print(json.dumps(result,ensure_ascii=False),flush=True)
        except BlockingIOError:
            print('Existing partner operation is active',flush=True)
        except Exception as exc:
            transient=any(text in str(exc) for text in ('Another catalogue sync','Code or operator','Uncommitted catalogue code'))
            save_json(STATE/args.source/'worker-error.json',{'at':stamp(),'error':type(exc).__name__+': '+str(exc),
                'requires_review':not transient,'parser_revision':parser_revision(),'published':False})
            raise
