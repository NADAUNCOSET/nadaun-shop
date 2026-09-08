"""Read-only partner readiness report. A scheduled process is not a live mirror."""
import hashlib
import json
from pathlib import Path
from sync_shop_sources import ROOT, OUT, stamp

STATE = ROOT / '_scraper/.sync-state'
PLAN = ROOT / '_scraper/partner-sync-plan.json'


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def verified_receipt(source, out=OUT, state=STATE):
    snapshot_path = out / (source + '.json')
    receipt = read(state / source / 'published.json')
    snapshot = read(snapshot_path)
    count = snapshot.get('product_count')
    if source == 'avx' and (snapshot.get('scope') != 'all' or not snapshot.get('catalogue_complete')):
        return False
    return bool(snapshot.get('complete') and isinstance(count, int) and count > 0
                and count == len(snapshot.get('products', {}))
                and receipt.get('verified_products') == count
                and all(receipt.get(key) for key in ('commit', 'deployment', 'revision', 'verified_at'))
                and receipt.get('source_sha256') == hashlib.sha256(snapshot_path.read_bytes()).hexdigest())


def report(plan_path=PLAN, out=OUT, state=STATE):
    sources = read(plan_path)['sources']
    result = {'checked_at': stamp(), 'sources': {}}
    for source, config in sources.items():
        folder = state / source
        generation = read(folder / 'generation.json') if source == 'avx' else {}
        progress = read(folder / generation.get('directory', '') / 'progress.json')
        published = verified_receipt(source, out, state)
        dependency = config.get('after_live_verified')
        waiting = dependency if dependency and not verified_receipt(dependency, out, state) else None
        adapter_ready = config.get('adapter') in ('plthink', 'avx')
        if source == 'avx':
            progress = progress | {'checked_at':progress.get('at'),
                'products_found':progress.get('expected'), 'details_verified':progress.get('verified_details')}
        # A receipt cannot turn an unimplemented adapter into recurring sync.
        source_choices = read(folder / 'publication-waiting.json') if source == 'avx' else {}
        phase = ('awaiting_brand_source_choices' if source_choices.get('state') == 'awaiting_brand_source_choices' and not published else
                 config.get('status','awaiting_source_access') if not adapter_ready else
                 'waiting_for_predecessor' if waiting else
                 'live_verified' if published else progress.get('phase', 'not_started'))
        result['sources'][source] = {
            'name': config['name'], 'phase': phase, 'waiting_for_live_source': waiting,
            'adapter_ready': adapter_ready, 'last_snapshot_live_verified': published,
            'automatic_refresh_implemented': adapter_ready,
            'refresh_interval_seconds': config.get('refresh_interval_seconds') if adapter_ready else None,
            'target_refresh_interval_seconds': config.get('target_refresh_interval_seconds'),
            'progress': {k: progress.get(k) for k in ('checked_at', 'brand_count', 'brands_checked', 'products_found', 'details_verified')},
            'last_worker_error': read(folder / 'worker-error.json' if source == 'avx' else state / (source + '-worker-error.json')) or None,
            'blocker': config.get('blocker') if not adapter_ready else None,
            'pending_brand_source_choices':len(source_choices.get('brands',[])),
        }
    return result


if __name__ == '__main__':
    print(json.dumps(report(), ensure_ascii=False, indent=2))
