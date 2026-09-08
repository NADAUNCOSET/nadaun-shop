"""Resume partner imports, then publish only a complete verified catalogue."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import time
from sync_shop_sources import ROOT, OUT, save_json, stamp
from sync_gift_inventory import Inventory, ensure_source_access
from gift_product_details import collect_details
from sync_plthink_catalog import collect_plthink, WORK
from shop_sync import STATE, CODE, command, managed_files, run, request, SITE


def changed_files():
    raw=subprocess.check_output(['git','status','--porcelain=v1','-z','--untracked-files=all'],cwd=ROOT)
    return {line[3:].decode() for line in raw.split(b'\0') if line}


def publish_ready(snapshot):
    if command('git','diff','--cached','--name-only'):raise RuntimeError('Staged operator edits prevent automatic publishing')
    if command('git','diff','--name-only','--',*CODE):raise RuntimeError('Uncommitted code prevents automatic publishing')
    unexpected=changed_files() & (set(managed_files())-{'data/catalog/sources/plthink.json'})
    if unexpected:raise RuntimeError('Generated files already have edits; automatic publishing needs review')
    result=run(existing=True)
    live=request('GET',SITE+'/data/catalog/catalog.json',params={'verify':result['revision']}).json()
    offers={o['id'] for p in live['products'] for o in p['offers'] if o['source']=='plthink'}
    if offers!=set(snapshot['products']):raise RuntimeError('Live PLTHINK products do not match the verified snapshot')
    if live['meta']['source_counts'].get('plthink')!=snapshot['product_count']:
        raise RuntimeError('Live PLTHINK source count is wrong')
    save_json(WORK/'published.json',result|{'source_collected_at':snapshot['collected_at'],
              'source_sha256':hashlib.sha256((OUT/'plthink.json').read_bytes()).hexdigest(),
              'verified_products':len(offers)})
    progress=json.loads((WORK/'progress.json').read_text()) if (WORK/'progress.json').exists() else {}
    save_json(WORK/'progress.json',progress|{'published':True,'live_verified_at':result['verified_at'],
              'commit':result['commit'],'deployment':result['deployment'],'revision':result['revision']})
    return result


def work(source):
    if source=='gift':
        ensure_source_access()
        inventory=Inventory()
        try:
            if not inventory.status()['inventory_complete']:inventory.scan()
            inventory.report()
        finally:inventory.db.close()
        collect_details()
        return
    path=OUT/'plthink.json'
    snapshot=json.loads(path.read_text()) if path.exists() else None
    receipt=json.loads((WORK/'published.json').read_text()) if (WORK/'published.json').exists() else {}
    if snapshot and snapshot.get('complete'):
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if receipt.get('source_sha256')!=digest:return publish_ready(snapshot)
        age=time.time()-datetime.fromisoformat(snapshot['collected_at']).timestamp()
        if age<12*3600:return
    snapshot=collect_plthink()
    return publish_ready(snapshot)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',choices=('gift','plthink'))
    args=parser.parse_args()
    try:work(args.source)
    except Exception as exc:
        save_json(STATE/(args.source+'-worker-error.json'),{'at':stamp(),'error':type(exc).__name__+': '+str(exc),'requires_review':True})
        raise


if __name__=='__main__':main()
