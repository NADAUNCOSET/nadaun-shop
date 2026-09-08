"""Resume AVX import, publish reconciled snapshots, refresh every 12 hours."""
import argparse
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time

from sync_avx_catalog import Importer, WORK, SourceSuspended
from sync_shop_sources import ROOT, OUT, save_json, stamp


def publish(snapshot):
    from brand_source_policy import pending,write_audit
    from avx_publication import partition
    approved,decisions=partition(snapshot)
    choices=pending(snapshot)
    save_json(WORK/'publication-selection.json',{'at':stamp(),**decisions})
    save_json(WORK/'publication-waiting.json',{'at':stamp(),'state':'awaiting_brand_source_choices' if choices else 'resolved',
        'brands':choices,'approved_products':approved['product_count'],'held_products':len(decisions['held_ids']),
        'owner_excluded_products':len(decisions['excluded_ids'])})
    if not approved['products']:
        write_audit(json.loads((ROOT/'data/catalog/catalog.json').read_text()),snapshot)
        return {'state':'awaiting_brand_source_choices','brands':len(choices)}
    prior=json.loads((WORK/'published.json').read_text()) if (WORK/'published.json').exists() else {}
    if snapshot['product_count']<prior.get('source_verified_products',0)*.85:
        raise RuntimeError('AVX full inventory decreased more than 15%; preserve previous publication and review')
    from shop_sync import CODE, command, managed_files, run, request, SITE
    from partner_worker import changed_files
    if command('git','diff','--cached','--name-only') or command('git','diff','--name-only','--',*CODE):
        raise RuntimeError('Reviewed commit required before AVX automatic publish')
    allowed={'data/catalog/sources/avx.json','data/catalog/sources/avx-aputure.json','data/catalog/sources/avx-approved.json'}
    if changed_files() & (set(managed_files())-allowed):
        raise RuntimeError('Existing generated edits require review before AVX publish')
    save_json(OUT/'avx-approved.json',approved)
    result=run(existing=True)
    live=request('GET',SITE+'/data/catalog/catalog.json',params={'verify':result['revision']}).json()
    ids={o['id'] for p in live['products'] for o in p['offers'] if o['source']=='avx'}
    if ids!=set(approved['products']):raise RuntimeError('AVX live IDs do not match approved source partition')
    # Unresolved and owner-excluded sources may never leak into public offers.
    if ids & (set(decisions['held_ids'])|set(decisions['excluded_ids'])):raise RuntimeError('Unapproved AVX product appeared in public offers')
    receipt=result|{'scope':approved['scope'],'verified_products':len(ids),
                    'source_file':'avx-approved.json','source_verified_products':snapshot['product_count'],
                    'pending_brand_count':len(decisions['pending_brands']),
                    'pending_product_count':len(decisions['held_ids']),
                    'owner_excluded_product_count':len(decisions['excluded_ids']),
                    'policy_sha256':decisions['policy_sha256'],
                    'source_collected_at':snapshot['collected_at'],
                    'source_sha256':hashlib.sha256((OUT/'avx-approved.json').read_bytes()).hexdigest()}
    save_json(WORK/'published.json',receipt)
    return receipt


def work():
    WORK.mkdir(parents=True,exist_ok=True)
    if (WORK/'source-suspended.json').exists():raise SourceSuspended('AVX provider review required')
    with (WORK/'worker.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        current=WORK/'generation.json'
        folder=WORK
        if current.exists():folder=WORK/json.loads(current.read_text())['directory']
        candidate=folder/'catalogue-candidate.json'
        snapshot=json.loads(candidate.read_text()) if candidate.exists() else json.loads((OUT/'avx.json').read_text()) if (OUT/'avx.json').exists() else None
        if snapshot and (folder/'all-complete.json').exists():
            receipt=json.loads((WORK/'published.json').read_text()) if (WORK/'published.json').exists() else {}
            from avx_publication import policy_fingerprint
            if receipt.get('source_collected_at')!=snapshot['collected_at'] or receipt.get('policy_sha256')!=policy_fingerprint():return publish(snapshot)
            if time.time()-datetime.fromisoformat(snapshot['collected_at']).timestamp()<12*3600:return
            folder=WORK/('generation-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
            folder.mkdir()
            save_json(current,{'directory':folder.name,'started_at':stamp()})
        importer=Importer(folder)
        # One provider-wide protection latch, also for future generations.
        importer.source.work=WORK
        try:snapshot=importer.collect('all')
        finally:importer.db.close()
        return publish(snapshot)


def install():
    label='co.nadaun.shop.avx-sync';target=Path.home()/'Library/LaunchAgents'/f'{label}.plist'
    status=subprocess.run(['launchctl','print',f'gui/{os.getuid()}/{label}'],capture_output=True)
    if status.returncode==0:raise RuntimeError('AVX worker already installed; inspect before replacing')
    logs=Path.home()/'Library/Logs/NADAUN/shop';logs.mkdir(parents=True,exist_ok=True)
    awake=shutil.which('caffeinate')
    if not awake:raise RuntimeError('caffeinate is required')
    entry=Path(__file__).resolve()
    definition={'Label':label,'ProgramArguments':[awake,'-i',sys.executable,str(entry)],
        'WorkingDirectory':str(Path.home()),'RunAtLoad':True,'StartInterval':600,'ProcessType':'Standard',
        'StandardOutPath':str(logs/'avx.stdout.log'),'StandardErrorPath':str(logs/'avx.stderr.log'),
        'EnvironmentVariables':{'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTHONUNBUFFERED':'1'}}
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('wb') as f:plistlib.dump(definition,f)
    subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(target)],check=True)
    loaded=subprocess.check_output(['launchctl','print',f'gui/{os.getuid()}/{label}'],text=True)
    if str(entry) not in loaded:raise RuntimeError('AVX NAS worker entrypoint not loaded')
    save_json(WORK/'schedule.json',{'at':stamp(),'label':label,'resume_seconds':600,'refresh_seconds':43200,
        'request_interval_seconds':3,'requires':'Mac awake, NAS mounted, network available'})
    print('AVX worker installed and loaded',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--install',action='store_true');args=parser.parse_args()
    if args.install:install()
    else:
        try:work()
        except Exception as exc:
            save_json(WORK/'worker-error.json',{'at':stamp(),'error':type(exc).__name__+': '+str(exc),'complete':False})
            raise
