"""Choose brand navigation independently of product/offer identity and price.

Original category IDs remain addressable. Uncovered products use another
verified source's tree; no product is assigned a guessed category.
"""
from collections import defaultdict
import re
import unicodedata


def normalized(value):
    return re.sub(r'[\s_\W]+', '', unicodedata.normalize('NFKC', str(value)).casefold())


GENERIC = {normalized(s) for s in (
    '전체', '전체보기', '전체상품', '상품', '브랜드', '제품', 'all', 'all products',
    '카메라/캠코더용품', '카메라/캠코더 관련용품', '기타카메라/캠코더용품',
    '디지털/가전', '카메라/캠코더', '기타', '액세서리', 'accessories')}


def choose_navigation(products, categories, brands, overrides=None):
    """Annotate navigation only; leave offers, original paths and rentals intact."""
    overrides = overrides or {}
    groups = defaultdict(list)
    for p in products:
        if p['kind'] == 'purchase':
            groups[p['brand_id']].append(p)
    audit = {'schema_version': 1, 'brands': {}}
    for bid, rows in groups.items():
        brand = brands[bid]
        aliases = {normalized(s) for s in [brand['name'], bid, *brand.get('aliases', [])]}
        paths = {}

        def path(cid):
            if cid in paths:
                return paths[cid]
            result, seen, current = [], set(), cid
            source = cid.split(':', 1)[0]
            while current:
                c = categories.get(current)
                if not c or current in seen or c.get('brand_id') != bid or current.split(':', 1)[0] != source:
                    raise ValueError('Invalid brand category ancestry: ' + cid)
                seen.add(current); result.insert(0, current); current = c.get('parent_id')
            paths[cid] = result
            return result

        families, other_brand_paths = {}, []
        for p in rows:
            family = families.setdefault(p.get('listing_id', p['id']), defaultdict(set))
            for cid in p.get('category_ids', []):
                if cid in categories and categories[cid].get('brand_id') != bid:
                    other_brand_paths.append({'product_id': p['id'], 'category_id': cid})
                    continue
                family[cid.split(':', 1)[0]].update(path(cid))
        candidates = {}
        for source in sorted({s for f in families.values() for s in f}):
            covered = specific = depth_total = 0
            leaves = set()
            for family in families.values():
                ids = family.get(source, set())
                if not ids:
                    continue
                covered += 1
                parents = {categories[c].get('parent_id') for c in ids}
                endpoints = ids - parents
                depths = []
                for cid in endpoints:
                    names = [normalized(categories[c]['name']) for c in path(cid)]
                    # Adding brand/all/other wrapper levels cannot inflate quality.
                    meaningful = [n for n in names if n not in GENERIC | aliases and not n.startswith('기타')]
                    leaf = names[-1]
                    depth = min(3, len(set(meaningful))) if leaf in meaningful else 0
                    depths.append(depth)
                    if depth:
                        leaves.add(tuple(meaningful))
                best = max(depths, default=0)
                specific += bool(best); depth_total += best
            candidates[source] = {'covered_products': covered, 'specific_products': specific,
                                  'depth_total': depth_total, 'distinct_paths': len(leaves),
                                  'score': specific * 4 + depth_total}
        order = sorted(candidates, key=lambda s: (-candidates[s]['score'],
                       -candidates[s]['covered_products'], -candidates[s]['distinct_paths'], s))
        requested = overrides.get(bid)
        if requested:
            if requested not in order:
                raise ValueError('Preferred category source has no verified membership: ' + bid + '/' + requested)
            order.remove(requested); order.insert(0, requested)
        preferred = order[0] if order else None
        chosen, used, fallback = {}, set(), 0
        for fid, family in families.items():
            source = next((s for s in order if family.get(s)), None)
            ids = sorted(family[source]) if source else []
            chosen[fid] = ids; used.update(ids)
            fallback += bool(source and source != preferred)
        for p in rows:
            p['navigation_category_ids'] = chosen[p.get('listing_id', p['id'])]
        brand['navigation_category_ids'] = sorted(used)
        audit['brands'][bid] = {'preferred_source': preferred, 'selection': 'override' if requested else 'coverage_and_specificity',
                               'listing_count': len(families), 'fallback_products': fallback,
                               'unclassified_products': sum(not ids for ids in chosen.values()),
                               'other_brand_paths_excluded': other_brand_paths, 'candidates': candidates}
    return audit
