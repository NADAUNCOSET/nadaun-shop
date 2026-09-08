"""Keep supplier refresh receipts separate from storefront/UI deployments."""
from datetime import datetime
import hashlib
import json
import time
from sync_shop_sources import ROOT, OUT, save_json, stamp

STATE=ROOT/'_scraper/.sync-state'
RECEIPT=STATE/'source-refresh-success.json'
SOURCES=('smartstore','imweb-dji','imweb-promotions','kpp','l-mount')


def fingerprints(out=OUT):
    return {source:hashlib.sha256((out/(source+'.json')).read_bytes()).hexdigest() for source in SOURCES}


def recent_refresh(receipt=RECEIPT,out=OUT,now=None):
    """A recent page deployment alone must never suppress a supplier refresh."""
    if not receipt.exists():return False
    try:
        data=json.loads(receipt.read_text())
        age=(time.time() if now is None else now)-datetime.fromisoformat(data['completed_at']).timestamp()
        return bool(0<=age<6*3600 and data.get('live_verified') and
                    data.get('source_sha256')==fingerprints(out))
    except (ValueError,KeyError,OSError,TypeError):return False


def record_refresh(release,receipt=RECEIPT,out=OUT):
    if not all(release.get(k) for k in ('commit','deployment','revision','verified_at')):
        raise ValueError('Source refresh requires a verified live deployment')
    data={'completed_at':stamp(),'source_sha256':fingerprints(out),
          'live_verified':True,'release':release,
          'source_collected_at':{s:json.loads((out/(s+'.json')).read_text())['collected_at'] for s in SOURCES}}
    save_json(receipt,data)
    return data
