"""Bind source-complete catalogue data to the exact files deployed by Vercel."""
import hashlib
from pathlib import Path


def write_manifest(root,catalog,snapshots,choices):
    from sync_shop_sources import save_json
    from brand_source_policy import publishable_ids
    files=['data/catalog/catalog.json','data/catalog/brands.json','data/catalog/rental.json','data/catalog/sync-status.json']
    files += [str(p.relative_to(root)) for p in (root/'data/catalog/details').glob('??.json')]
    import json
    from inline_product_images import referenced_paths
    details={Path(p).stem:json.loads((root/p).read_text()) for p in files if p.startswith('data/catalog/details/')}
    files += referenced_paths(catalog['products'],details)
    # Private source data is excluded from the deployment. Only identities and
    # digests needed to prove completeness are copied into the server manifest.
    inventories={}
    for source in ('hipixel','motion9','funomad'):
        if source in snapshots:
            ids=sorted(publishable_ids(snapshots[source]))
            inventories[source]={'count':len(ids),'sha256':hashlib.sha256('\n'.join(ids).encode()).hexdigest()}
    manifest={'schema_version':1,'revision':catalog['meta']['revision'],'require_positions':True,
        'brand_order':[b['id'] for b in catalog['brands']],
        'primary_sources':{bid:c['source'] for bid,c in choices.items()},
        'main_sources':{bid:c.get('main_sources') or [c['source']] for bid,c in choices.items()},
        'source_inventories':inventories,
        'files':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sorted(files)}}
    save_json(root/'server/catalog-release.json',manifest)
    return manifest
