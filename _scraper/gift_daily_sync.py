"""Offline, identity-preserving gift mirror reconciliation.

A Naver feed is a partial sales channel, not a deletion manifest. Only a
validated full source inventory or an explicit source withdrawal removes a
listing. Historical products, detail snapshots and order IDs are retained.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from gift_official_feed import parse_feed

SOURCE = 'https://nadaun-gift.com/naver/dburl/auto_up/nadaun-gift.com_all_up.txt'
ID = re.compile(r'[1-9][0-9]{0,11}')
STATES = {'unverified', 'feed_present', 'pending_absence', 'withdrawn'}


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Source observation must include a timezone')
    return parsed.astimezone(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def public_image(value):
    p = urlsplit(value)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Invalid public image URL')
    return value


def validate_download(raw, prior_count=0, minimum_count=1000):
    # Newline and cardinality guards also catch many truncated HTTP200 files.
    if not raw.endswith((b'\n', b'\r')):
        raise ValueError('Feed is truncated: missing final newline')
    rows, rejected = parse_feed(raw)
    count = len(rows) + len(rejected)
    if count < minimum_count or prior_count and count < prior_count * .95:
        raise ValueError('Unexpected source inventory drop; preserve published catalog')
    if len(rejected) > max(10, count * .001):
        raise ValueError('Too many malformed source rows; preserve published catalog')
    quarantined = set()
    for item in rejected:
        pid = item['raw_fields'][0]
        if not ID.fullmatch(pid):
            raise ValueError('Cannot identify quarantined source product')
        quarantined.add(pid)
    return rows, rejected, quarantined


def apply_feed(catalog, raw, *, observed_at, modified_at, minimum_count=1000):
    """Return new catalog and receipt; never mutate the input or unit prices."""
    observed, modified = timestamp(observed_at), timestamp(modified_at)
    if modified > observed:
        raise ValueError('Source modification time is in the future')
    previous = catalog.get('meta', {}).get('mirror', {})
    if previous.get('source_modified_at') and modified < timestamp(previous['source_modified_at']):
        raise ValueError('Older source snapshot cannot overwrite current state')
    rows, rejected, quarantined = validate_download(
        raw, catalog.get('meta', {}).get('official_feed_count', 0), minimum_count)
    result = deepcopy(catalog)
    products = {p['id']: p for p in result['products']}
    if len(products) != len(result['products']) or any(not ID.fullmatch(p) for p in products):
        raise ValueError('Existing catalog identity conflict')
    cats = {c['id']: c for c in result['categories']}
    by_label = defaultdict(list)
    for c in cats.values():
        by_label[c['name'].strip()].append(c['id'])
    present, added, changed = set(), [], []
    sha = hashlib.sha256(raw).hexdigest()
    same_snapshot = previous.get('source_sha256') == sha and previous.get('source_modified_at') == modified_at
    for row in rows:
        pid = row['id']; present.add(pid)
        label = row['category_name1'].strip()
        matching = by_label.get(label, [])
        cid = matching[0] if len(matching) == 1 else None
        if cid is None and pid in products:
            cid = products[pid]['category_ids'][-1]
        if cid is None:
            cid = 'feed-' + hashlib.sha256(label.encode()).hexdigest()[:12]
            cats.setdefault('feed', {'id': 'feed', 'name': '본사 제공 상품', 'parent_ids': [], 'count': 0})
            cats.setdefault(cid, {'id': cid, 'name': label or '분류 확인 중', 'parent_ids': ['feed'], 'count': 0})
            by_label[label] = [cid]
        source_fields = {'name': row['title'].strip(), 'image': public_image(row['image_link']),
                         'manufacturer_label': row['maker'].strip(), 'origin': row['origin'].strip(),
                         'feed_category': label}
        if pid not in products:
            products[pid] = {'id': pid, 'detail_available': False, 'soldout': None,
                            'category_ids': list(dict.fromkeys([*cats[cid]['parent_ids'], cid]))}
            added.append(pid)
        p = products[pid]
        if any(p.get(k) != v for k, v in source_fields.items()):
            changed.append(pid)
        # An ambiguous feed category never discards a verified category path.
        if p.get('feed_category') != label and len(matching) == 1:
            p['category_ids'] = list(dict.fromkeys([*cats[cid]['parent_ids'], cid]))
        p.update(source_fields)
        p['feed_observed_at'] = observed_at
        # A newer feed explicitly containing the ID can restore a withdrawal.
        if p.get('source_status') != 'withdrawn' or modified > timestamp(p['source_status_at']):
            p.update(source_status='feed_present', source_status_at=modified_at)
            for k in ('source_missing_since', 'source_missing_snapshots'):
                p.pop(k, None)
    pending = []
    for pid, p in products.items():
        if pid in present or pid in quarantined:
            continue
        if p.get('source_status') == 'withdrawn':
            continue
        if p.get('feed_observed_at') or p.get('source_status') in ('feed_present', 'pending_absence'):
            p.setdefault('source_missing_since', modified_at)
            p['source_missing_snapshots'] = p.get('source_missing_snapshots', 0) + (not same_snapshot)
            p['source_status'] = 'pending_absence'
            pending.append(pid)
        else:
            p['source_status'] = 'unverified'
    result['products'] = sorted(products.values(), key=lambda p: int(p['id']), reverse=True)
    result['categories'] = list(cats.values())
    result['meta'].update(official_feed_count=len(rows), official_feed_added=len(added),
                          official_feed_observed_at=observed_at, official_feed_sha256=sha,
                          automatic_source_refresh=False, all_current_details_verified=False)
    result['meta']['mirror'] = {
        'source': 'nadaun-gift', 'source_modified_at': modified_at, 'source_sha256': sha,
        'last_feed_check_at': observed_at, 'source_scope': 'naver_channel_subset',
        'full_source_inventory_verified': False, 'exact_id_matches': len(present),
        'quarantined_count': len(rejected), 'pending_absence_count': len(pending),
        'daily_refresh_requested': True, 'daily_refresh_state': 'awaiting_source_access',
        'withdrawal_policy': 'confirmed_full_inventory_or_explicit_source_withdrawal',
    }
    refresh_metadata(result)
    receipt = {'source_sha256': sha, 'observed_at': observed_at, 'modified_at': modified_at,
               'valid_rows': len(rows), 'quarantined_rows': len(rejected), 'quarantined_ids': sorted(quarantined),
               'added_ids': added, 'changed_ids': changed, 'pending_absence_ids': pending,
               'withdrawn_ids': [], 'all_details_current': False}
    return result, receipt


def apply_availability(catalog, evidence):
    """Apply an authenticated/exported source inventory, with exact SKU proof.

    The importer must retain the original source document by its sha256. A
    Naver feed can never be promoted to a full inventory by this function.
    """
    required = {'kind', 'source', 'observed_at', 'source_sha256', 'products'}
    if not required <= set(evidence) or evidence['source'] != 'nadaun-gift':
        raise ValueError('Source identity and evidence are required')
    if evidence['kind'] not in ('authenticated_full_inventory', 'explicit_product_status'):
        raise ValueError('Naver feed absence is not withdrawal evidence')
    if not re.fullmatch(r'[a-f0-9]{64}', evidence['source_sha256']):
        raise ValueError('Original source checksum required')
    at = timestamp(evidence['observed_at'])
    rows = evidence['products']
    if not isinstance(rows, list) or not rows:
        raise ValueError('Empty source inventory cannot remove the catalog')
    indexed = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not ID.fullmatch(row['id']):
            raise ValueError('Invalid source product ID')
        if row['id'] in indexed or row.get('status') not in ('active', 'soldout', 'withdrawn'):
            raise ValueError('Duplicate product or invalid availability')
        indexed[row['id']] = row['status']
    full = evidence['kind'] == 'authenticated_full_inventory'
    if full and (evidence.get('complete') is not True or evidence.get('advertised_total') != len(rows)):
        raise ValueError('Full inventory coverage not established')
    result = deepcopy(catalog); changes = []
    if set(indexed) - {p['id'] for p in result['products']}:
        raise ValueError('Unmatched source IDs must be imported before availability changes')
    if full:
        prior_full = result['meta'].get('mirror', {}).get('full_inventory_count')
        baseline = prior_full or result['meta'].get('official_feed_count', 0)
        if baseline and len(rows) < baseline * .95:
            raise ValueError('Mass source removal requires review')
    for p in result['products']:
        old_at = p.get('source_status_at')
        if old_at and at < timestamp(old_at):
            if p['id'] in indexed or full:
                raise ValueError('Older availability would overwrite newer source evidence')
        status = indexed.get(p['id'], 'withdrawn' if full else None)
        if status is None:
            continue
        before = (p.get('source_status'), p.get('soldout'))
        p.update(source_status='withdrawn' if status == 'withdrawn' else 'feed_present',
                 source_status_at=evidence['observed_at'], soldout=status == 'soldout')
        if before != (p['source_status'], p['soldout']):
            changes.append(p['id'])
    mirror = result['meta'].setdefault('mirror', {})
    mirror.update(last_availability_check_at=evidence['observed_at'])
    if full:
        mirror.update(full_source_inventory_verified=True, full_inventory_count=len(rows))
    refresh_metadata(result)
    return result, changes


def refresh_metadata(catalog):
    active = [p for p in catalog['products'] if p.get('source_status') != 'withdrawn']
    counts = Counter(cid for p in active for cid in p['category_ids'])
    first = {}
    for p in active:
        for cid in p['category_ids']:
            first.setdefault(cid, p)
    for c in catalog['categories']:
        c['count'] = counts[c['id']]
        if c['id'] in first:
            p = first[c['id']]; c.update(image=p['image'], product_id=p['id'])
    meta = catalog['meta']
    meta.update(product_count=len(catalog['products']), active_product_count=len(active),
                withdrawn_product_count=len(catalog['products'])-len(active),
                category_count=len(catalog['categories']),
                leaf_category_count=sum(bool(c['parent_ids']) for c in catalog['categories']))
    meta.pop('revision', None)
    meta['revision'] = digest(catalog)[:16]


def write_catalog(root, catalog):
    root = Path(root); folder = root / 'data/gift'
    folder.mkdir(parents=True, exist_ok=True)
    values = {'catalog.json': catalog,
              'manifest.json': {'meta': catalog['meta'], 'categories': catalog['categories']},
              'sync-status.json': {'meta': catalog['meta']}}
    for name, data in values.items():
        (folder / name).write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':'))+'\n')
    urls = ['https://shop.nadaun.co/gifts.html'] + [
        'https://shop.nadaun.co/gifts.html?category='+c['id'] for c in catalog['categories'] if c['count']]+[
        'https://shop.nadaun.co/gift-item.html?id='+p['id'] for p in catalog['products']
        if p.get('source_status') != 'withdrawn']
    files = []
    for i in range(0, len(urls), 40000):
        name = f'gift-sitemap-{i//40000+1}.xml'; files.append(name)
        (root/name).write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(
            '<url><loc>'+escape(url)+'</loc></url>' for url in urls[i:i+40000])+'</urlset>\n')
    # Stale old sitemap files are emptied, not left with withdrawn product URLs.
    for path in root.glob('gift-sitemap-*.xml'):
        if path.name not in files:
            path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>\n')
    (root/'gift-sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(
        '<sitemap><loc>https://shop.nadaun.co/'+name+'</loc></sitemap>' for name in files)+'</sitemapindex>\n')
