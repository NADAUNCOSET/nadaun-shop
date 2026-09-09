"""Resume partner imports, then publish only a complete verified catalogue."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import time
from sync_shop_sources import ROOT, OUT, save_json, stamp
from sync_gift_inventory import Inventory, ensure_source_access
from gift_product_details import collect_details
from sync_plthink_catalog import collect_plthink, WORK
from shop_sync import STATE, run, request, SITE
from brand_source_policy import publishable_ids, policy_fingerprint


def publish_ready(snapshot):
    result=run(existing=True,source_updates={'plthink':snapshot})
    live=request('GET',SITE+'/data/catalog/catalog.json',params={'verify':result['revision']}).json()
    offers={o['id'] for p in live['products'] for o in p['offers'] if o['source']=='plthink'}
    expected=publishable_ids(snapshot)
    if offers!=expected:raise RuntimeError('Live PLTHINK products do not match the owner-selected source scope')
    if live['meta']['source_counts'].get('plthink')!=snapshot['product_count']:
        raise RuntimeError('Live PLTHINK source count is wrong')
    save_json(WORK/'published.json',result|{'source_collected_at':snapshot['collected_at'],
              'source_sha256':hashlib.sha256((OUT/'plthink.json').read_bytes()).hexdigest(),
              'verified_products':len(offers),'source_verified_products':snapshot['product_count'],
              'excluded_ids':sorted(set(snapshot['products'])-expected),'policy_sha256':policy_fingerprint()})
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
    candidate=WORK/'catalogue-candidate.json'
    if candidate.exists():
        pending=json.loads(candidate.read_text())
        published_at=receipt.get('source_collected_at')
        if not published_at or datetime.fromisoformat(pending['collected_at'])>datetime.fromisoformat(published_at):
            return publish_ready(pending)
    if snapshot and snapshot.get('complete'):
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if receipt.get('source_sha256')!=digest or receipt.get('policy_sha256')!=policy_fingerprint():return publish_ready(snapshot)
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
