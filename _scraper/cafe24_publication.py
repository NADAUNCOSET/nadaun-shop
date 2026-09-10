"""Validate full partner inventories and normalize their original brand trees."""
from copy import deepcopy
import hashlib
import json

from sync_cafe24_partners import SITES


def validate_candidate(snapshot):
    source = snapshot.get('source')
    count = snapshot.get('product_count')
    products = snapshot.get('products')
    if (source not in SITES or snapshot.get('complete') is not True or
            isinstance(count, bool) or not isinstance(count, int) or count < 1 or
            not isinstance(products, dict) or len(products) != count or
            snapshot.get('changed_categories') or snapshot.get('detail_errors') or snapshot.get('content_reviews')):
        raise ValueError('Partner candidate is not fully reconciled')
    coverage = snapshot.get('coverage', [])
    categories = snapshot.get('categories', [])
    root = SITES[source][1]
    if snapshot.get('normalized_for_shop'):
        raw_categories = snapshot.get('original_categories', [])
    else:
        raw_categories = categories
    category_ids = {node['id'] for node in raw_categories}
    if (len(category_ids) != len(raw_categories) or root not in category_ids or
            len(coverage) != len(category_ids) or {row['id'] for row in coverage} != category_ids or
            any(row['expected'] != row['unique'] for row in coverage) or
            next(row['unique'] for row in coverage if row['id'] == root) != count):
        raise ValueError('Partner category coverage does not match the inventory')
    for pid, product in products.items():
        if (pid != product.get('id') or pid != source + '-' + str(product.get('source_id')) or
                product.get('source') != source or product.get('kind') != 'purchase' or
                product.get('detail_status') != 'verified' or product.get('content_issues') or
                not product.get('brand') or product['brand'] == '미분류' or
                not product.get('detail_checked_at')):
            raise ValueError('Unverified partner identity or content: ' + pid)
    if not snapshot.get('collected_at'):
        raise ValueError('Missing source reconciliation timestamp')


def prepare(snapshot):
    validate_candidate(snapshot)
    if snapshot.get('normalized_for_shop'):
        return deepcopy(snapshot)
    from build_catalog import brand_id
    result = deepcopy(snapshot)
    source = result['source']; root = SITES[source][1]
    nodes = {node['id']: node for node in result['categories']}
    brand_roots = {brand_id(node['name']): node['name'] for node in nodes.values() if node['parent_id'] == root}
    categories = []
    for cid, node in nodes.items():
        if cid == root:
            continue
        current = cid; seen = set(); chosen = None
        while current != root:
            if current in seen or current not in nodes:
                raise ValueError('Invalid source brand ancestry')
            seen.add(current)
            ancestor = nodes[current]
            if brand_id(ancestor['name']) in brand_roots:
                chosen = ancestor['name']; break
            current = ancestor['parent_id']
        if not chosen:
            raise ValueError('Category has no original brand ancestor')
        # Explicit nested brand roots stand independently in the shop, while
        # original_categories retains the supplier's complete cross-brand tree.
        parent = None if current == cid else node['parent_id']
        categories.append({**node, 'parent_id': parent, 'brand': chosen})
    category_map = {node['id']: node for node in categories}
    for product in result['products'].values():
        memberships = product.get('brand_category_ids', [])
        if not any(cid in category_map and brand_id(category_map[cid]['brand']) == brand_id(product['brand']) for cid in memberships):
            # A Product schema may declare a brand omitted from the menu.
            cid = 'schema-brand-' + brand_id(product['brand'])
            if cid not in category_map:
                node = {'id': cid, 'name': product['brand'], 'brand': product['brand'], 'parent_id': None}
                category_map[cid] = node; categories.append(node)
            product['brand_category_ids'] = [*memberships, cid]
    result.update(original_categories=result['categories'], categories=categories,
                  normalized_for_shop=True, scope='all', catalogue_complete=True)
    result['candidate_sha256'] = digest(snapshot)
    return result


def digest(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
