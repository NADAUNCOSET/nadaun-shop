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
    if source=='avx' and (out/'avx-approved.json').exists():snapshot_path=out/'avx-approved.json'
    receipt = read(state / source / 'published.json')
    snapshot = read(snapshot_path)
    count = snapshot.get('product_count')
    if not isinstance(count,int) or count<1:return False
    if source == 'avx':
        if snapshot.get('scope')=='approved-brands':
            from avx_publication import policy_fingerprint
            publication=snapshot.get('publication',{})
            if (not publication.get('full_collection_verified') or publication.get('pending_brand_count')!=0 or
                publication.get('pending_product_count')!=0 or receipt.get('pending_brand_count')!=0 or
                publication.get('accepted_product_count')!=count or
                publication.get('source_product_count')!=count+publication.get('owner_excluded_product_count',0) or
                receipt.get('source_verified_products')!=publication.get('source_product_count') or
                receipt.get('policy_sha256')!=publication.get('policy_sha256') or
                receipt.get('policy_sha256')!=policy_fingerprint()):return False
        elif snapshot.get('scope')!='all' or not snapshot.get('catalogue_complete'):return False
    expected_count=count
    if source=='dji-official':
        from sync_dji_official import validate_snapshot,official_dji_ids
        from brand_source_policy import policy_fingerprint
        try:validate_snapshot(snapshot)
        except ValueError:return False
        expected=official_dji_ids(snapshot);expected_count=len(expected)
        if (receipt.get('held_other_brand_ids')!=sorted(set(snapshot['products'])-expected) or
            receipt.get('source_verified_products')!=count or receipt.get('policy_sha256')!=policy_fingerprint()):return False
    if source=='plthink':
        from brand_source_policy import publishable_ids,policy_fingerprint
        expected=publishable_ids(snapshot)
        if (len(expected)!=count or 'excluded_ids' in receipt) and (receipt.get('policy_sha256')!=policy_fingerprint() or
            receipt.get('excluded_ids')!=sorted(set(snapshot['products'])-expected) or
            receipt.get('source_verified_products')!=count):return False
        expected_count=len(expected)
    return bool(snapshot.get('complete') and isinstance(count, int) and count > 0
                and count == len(snapshot.get('products', {}))
                and receipt.get('verified_products') == expected_count
                and all(receipt.get(key) for key in ('commit', 'deployment', 'revision', 'verified_at'))
                and receipt.get('source_sha256') == hashlib.sha256(snapshot_path.read_bytes()).hexdigest())


def report(plan_path=PLAN, out=OUT, state=STATE):
    sources = read(plan_path)['sources']
    result = {'checked_at': stamp(), 'sources': {}}
    for source, config in sources.items():
        folder = state / source
        generation = read(folder / 'generation.json') if source in ('avx','dji-official') else {}
        progress = read(folder / generation.get('directory', '') / 'progress.json')
        published = verified_receipt(source, out, state)
        dependency = config.get('after_live_verified')
        waiting = dependency if dependency and not verified_receipt(dependency, out, state) else None
        adapter_ready = config.get('adapter') in ('plthink', 'avx', 'dji-official')
        collector_ready = config.get('collection_adapter') == 'cafe24'
        if collector_ready:progress=progress|{'checked_at':progress.get('at')}
        if source == 'avx':
            progress = progress | {'checked_at':progress.get('at'),
                'products_found':progress.get('expected'), 'details_verified':progress.get('verified_details')}
        if source=='dji-official':
            # DJI publishes current progress at provider level across generations.
            progress=read(folder/'progress.json')
            progress=progress|{'checked_at':progress.get('at')}
        # A receipt cannot turn an unimplemented adapter into recurring sync.
        source_choices = read(folder / 'publication-waiting.json') if source == 'avx' else {}
        receipt=read(folder/'published.json')
        phase = (source_choices['state'] if source_choices.get('state') in ('awaiting_brand_source_choices','awaiting_content_review') and not published else
                 progress.get('phase',config.get('status','not_started')) if collector_ready else
                 config.get('status','awaiting_source_access') if not adapter_ready else
                 'waiting_for_predecessor' if waiting else
                 'live_verified' if published else progress.get('phase', 'not_started'))
        result['sources'][source] = {
            'name': config['name'], 'phase': phase, 'waiting_for_live_source': waiting,
            'adapter_ready': adapter_ready, 'last_snapshot_live_verified': published,
            'collection_adapter_ready':collector_ready or adapter_ready,
            'automatic_refresh_implemented': adapter_ready,
            'refresh_interval_seconds': config.get('refresh_interval_seconds') if adapter_ready else None,
            'target_refresh_interval_seconds': config.get('target_refresh_interval_seconds'),
            'progress': {k: progress.get(k) for k in ('checked_at', 'brand_count', 'brands_checked', 'products_found', 'details_verified','categories_verified','categories_found','page','pages_in_category','details_parsed','detail_errors','content_reviews')},
            'last_worker_error': read(folder / 'worker-error.json' if source in ('avx','dji-official') or collector_ready else state / (source + '-worker-error.json')) or None,
            'blocker': config.get('blocker') if not adapter_ready else None,
            'pending_brand_source_choices':len(source_choices.get('brands',[])),
            'pending_source_content_reviews':len(source_choices.get('content_review_ids',{})),
            'held_other_brand_products':len(receipt.get('held_other_brand_ids',[])),
            'last_verified_published_products':receipt.get('verified_products'),
            'last_verified_source_products':receipt.get('source_verified_products'),
            'published_scope':receipt.get('scope'),
        }
    return result


if __name__ == '__main__':
    print(json.dumps(report(), ensure_ascii=False, indent=2))
