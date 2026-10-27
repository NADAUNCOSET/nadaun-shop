"""Refresh the two owner-scoped suppliers and publish complete snapshots only."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,os,sys,time
from pathlib import Path
from sync_shop_sources import ROOT,OUT,save_json,stamp
from sync_cafe24_partners import run_lock
from reviewed_supplier_sources import validate_snapshot,ids_digest

SOURCES=('digitalcp','sunphoto')
INTERVAL=12*3600

def normalize(snapshot):
    source=snapshot.get('source');result=deepcopy(snapshot)
    if source not in SOURCES or snapshot.get('complete') is not True:
        raise ValueError('Scoped supplier collection is incomplete')
    coverage=snapshot.get('coverage')
    if not isinstance(coverage,list) or not coverage or any(c.get('expected')!=c.get('unique') for c in coverage):
        raise ValueError('Scoped supplier category coverage differs')
    if source=='digitalcp' and snapshot.get('source_inventory_count')!=len(snapshot['products'])+sum(snapshot.get('excluded_counts',{}).values()):
        raise ValueError('DigitalCP owner scope partition differs')
    if source=='sunphoto' and snapshot.get('owner_brand_roots')!={'29':'TAMRON','30':'Voigtlander'}:
        raise ValueError('Sunphoto owner scope changed')
    result.update(schema_version=1,source_category_coverage=coverage,
        coverage={'count':len(snapshot['products']),'ids_sha256':ids_digest(snapshot['products'])})
    return validate_snapshot(result)

def read(path):return json.loads(path.read_text()) if path.exists() else {}
def publish(snapshot):
    from brand_source_policy import supplemental_source_approved,publishable_ids,policy_fingerprint
    if not supplemental_source_approved(snapshot['source']):raise ValueError('Supplier owner approval is missing')
    from shop_sync import run,request,SITE
    source=snapshot['source'];folder=ROOT/'_scraper/.sync-state'/source
    previous=read(OUT/(source+'.json'))
    if snapshot['product_count']<previous.get('product_count',0)*.85:
        raise ValueError('Supplier inventory decreased over15%; exact retirement review required')
    result=run(existing=True,source_updates={source:snapshot})
    actual=request('GET',SITE+'/data/catalog/catalog.json',params={'verify':result['revision']}).json()
    ids={o['id'] for p in actual['products'] for o in p['offers'] if o['source']==source}
    if ids!=publishable_ids(snapshot):raise ValueError('Published supplier identities differ from reviewed scope')
    receipt=result|{'source':source,'source_collected_at':snapshot['collected_at'],
        'source_sha256':hashlib.sha256((OUT/(source+'.json')).read_bytes()).hexdigest(),
        'verified_products':len(ids),'policy_sha256':policy_fingerprint()}
    save_json(folder/'published.json',receipt);return receipt

def work(source):
    if source not in SOURCES:raise ValueError('Unsupported scoped supplier')
    folder=ROOT/'_scraper/.sync-state'/source;folder.mkdir(parents=True,exist_ok=True)
    control=folder/'worker-control';control.mkdir(exist_ok=True)
    with run_lock(control):
        if (folder/'source-suspended.json').exists():return {'phase':'source_suspended','requests':0}
        if read(folder/'worker-error.json').get('requires_review'):return {'phase':'error_requires_review','requests':0}
        saved=read(OUT/(source+'.json'));receipt=read(folder/'published.json')
        age=time.time()-datetime.fromisoformat(saved['collected_at']).timestamp() if saved else INTERVAL
        if saved and 0<=age<INTERVAL:
            if not receipt:return {'phase':'awaiting_initial_live_verification','requests':0}
            from brand_source_policy import policy_fingerprint
            if (receipt.get('source_sha256')==hashlib.sha256((OUT/(source+'.json')).read_bytes()).hexdigest()
                and receipt.get('policy_sha256')==policy_fingerprint()):
                return {'phase':'current','requests':0,'next_refresh_seconds':int(INTERVAL-age)}
            return publish(validate_snapshot(saved))
        generation=read(folder/'generation.json')
        if not generation:
            name='generation-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
            save_json(folder/'generation.json',{'directory':name});generation={'directory':name}
        path=folder/generation['directory']
        try:
            if source=='digitalcp':from sync_digitalcp_catalog import collect
            else:from sync_sunphoto_catalog import collect
            snapshot=normalize(collect(path));result=publish(snapshot)
        except Exception:
            if (path/'source-suspended.json').exists():
                save_json(folder/'source-suspended.json',read(path/'source-suspended.json')|{'automatic_resume':False})
            raise
        (folder/'generation.json').unlink(missing_ok=True)
        return result

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('source',choices=SOURCES);args=parser.parse_args()
    try:result=work(args.source);print(json.dumps(result,ensure_ascii=False),flush=True)
    except Exception as exc:
        from cafe24_worker import retryable_error
        save_json(ROOT/'_scraper/.sync-state'/args.source/'worker-error.json',
            {'at':stamp(),'requires_review':not retryable_error(exc),'error':type(exc).__name__+': '+str(exc)})
        raise
