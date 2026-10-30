"""Owner-approved five-day supplier cadence; attempts never imply fresh data."""
from datetime import datetime,timezone
import json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_INTERVAL=5*24*3600

def read(path,default=None):
    path=Path(path)
    return json.loads(path.read_text()) if path.is_file() else ({} if default is None else default)

def policy(root=ROOT):
    value=read(Path(root)/'_scraper/mirror-policy.json')
    if value.get('confirmed_by')!='owner' or value.get('schema_version')!=1:
        raise ValueError('Missing owner-approved mirror cadence')
    if value.get('refresh_interval_seconds')!=DEFAULT_INTERVAL:
        raise ValueError('Supplier cadence must be the approved five days')
    if value.get('collection_concurrency')!=1 or value.get('failed_or_partial_inventory_removes_products') is not False:
        raise ValueError('Unsafe mirror execution policy')
    return value

def interval_seconds(source=None,root=ROOT):
    value=policy(root)['refresh_interval_seconds']
    configured=read(Path(root)/'_scraper/partner-sync-plan.json').get('sources',{}).get(source,{})
    period=configured.get('refresh_interval_seconds',value)
    if not isinstance(period,int) or isinstance(period,bool) or not 0<period<=value:
        raise ValueError('Supplier interval exceeds five days: '+str(source))
    return period

def timestamp(value):
    if not isinstance(value,str):return None
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00'))
        return result.timestamp() if result.tzinfo else None
    except ValueError:return None

def freshness(snapshot,source=None,root=ROOT,now=None):
    now=datetime.now(timezone.utc).timestamp() if now is None else now
    observed=timestamp(snapshot.get('collected_at'));period=interval_seconds(source,root)
    age=now-observed if observed is not None else None
    valid=age is not None and age>=0
    complete=snapshot.get('complete') is True
    due=not valid or not complete or age>=period
    return {'source_collected_at':snapshot.get('collected_at'),'age_seconds':round(age) if valid else None,
            'refresh_interval_seconds':period,'due':due,
            'next_due_at':datetime.fromtimestamp(observed+period,timezone.utc).isoformat() if valid and complete else None,
            'source_time_invalid':not valid,'snapshot_complete':complete}

def source_path(source,root=ROOT):
    base=Path(root)/'data/catalog/sources'
    if source=='avx':
        for name in ['avx-approved.json','avx.json','avx-aputure.json']:
            if (base/name).is_file():return base/name
    return base/(source+'.json')

def controls(source,root=ROOT):
    root=Path(root);folder=root/'_scraper/.sync-state'/source
    suspension=read(folder/'source-suspended.json');error=read(folder/'worker-error.json')
    if not error:error=read(root/'_scraper/.sync-state'/(source+'-worker-error.json'))
    if suspension and suspension.get('suspended',True):
        return {'blocked':True,'phase':'source_suspended','reason':suspension.get('reason') or suspension.get('error') or 'Existing source access/owner hold','evidence':str(folder/'source-suspended.json')}
    if error.get('requires_review') and not error.get('resolved'):
        return {'blocked':True,'phase':'error_requires_review','reason':error.get('error','Source interpretation requires review'),'evidence':str(folder/'worker-error.json')}
    return {'blocked':False}

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name('.'+path.name+'.pending-'+str(os.getpid()))
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');os.replace(temporary,path)
