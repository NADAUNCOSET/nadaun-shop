"""Validate full partner inventories and normalize their original brand trees."""
from copy import deepcopy
import hashlib
import json

from sync_cafe24_partners import SITES, WHOLE_SITE


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
    if source in WHOLE_SITE:
        nodes={node['id']:node for node in raw_categories}
        if not nodes[root].get('synthetic') or nodes[root]['parent_id'] is not None:
            raise ValueError('Whole-site evidence root is missing')
        union=next(row for row in coverage if row['id']==root)
        if not union.get('derived_union') or union.get('pages')!=0:
            raise ValueError('Whole-site union cannot be claimed as an advertised category')
        counts={cid:0 for cid in nodes if cid!=root}
        for product in products.values():
            memberships=product.get('original_category_ids') if snapshot.get('normalized_for_shop') else product.get('brand_category_ids')
            if not memberships or len(memberships)!=len(set(memberships)) or not set(memberships)<=set(counts):
                raise ValueError('Whole-site product categories are unverified: '+product['id'])
            for cid in memberships:counts[cid]+=1
        if any(row['unique']!=counts[row['id']] for row in coverage if row['id']!=root):
            raise ValueError('Whole-site membership differs from source category counts')
        if snapshot.get('normalized_for_shop'):
            from build_catalog import brand_id
            if source == 'ldnet' and snapshot.get('brand_classification_revision'):
                from ldnet_identity import resolve, revision
                if snapshot['brand_classification_revision'] == revision():
                    for product in products.values():
                        expected_brand, evidence = resolve(product, nodes)
                        if product['brand'] != expected_brand or product.get('brand_evidence') != evidence:
                            raise ValueError('LDNET product brand differs from source evidence: '+product['id'])
            expected=set()
            for product in products.values():
                bid=brand_id(product['brand']);original=product['original_category_ids']
                if product['brand_category_ids']!=[bid+':'+cid for cid in original]:
                    raise ValueError('Normalized product category identity changed')
                for cid in original:
                    cursor=cid;seen=set()
                    while cursor!=root:
                        if cursor in seen or cursor not in nodes:raise ValueError('Original source ancestry is invalid')
                        seen.add(cursor);expected.add(bid+':'+cursor);cursor=nodes[cursor]['parent_id']
            if {node['id'] for node in categories}!=expected or len(categories)!=len(expected):
                raise ValueError('Normalized source paths are incomplete or duplicated')
            for node in categories:
                original=nodes.get(node.get('source_category_id'));bid=brand_id(node['brand'])
                if not original or original['id']==root or (node['id'],node['name'],node['parent_id'])!=(
                    bid+':'+original['id'],original['name'],bid+':'+original['parent_id'] if original['parent_id']!=root else None):
                    raise ValueError('Normalized source label or ancestry changed')
    if not snapshot.get('collected_at'):
        raise ValueError('Missing source reconciliation timestamp')


def prepare(snapshot):
    validate_candidate(snapshot)
    if snapshot.get('normalized_for_shop'):
        if snapshot['source'] != 'ldnet':
            return deepcopy(snapshot)
        from ldnet_identity import revision
        if snapshot.get('brand_classification_revision') == revision():
            return deepcopy(snapshot)
        # Rebuild the old manufacturer-based paths from preserved source IDs.
        snapshot = deepcopy(snapshot)
        snapshot['categories'] = snapshot.pop('original_categories')
        snapshot.pop('normalized_for_shop')
        for product in snapshot['products'].values():
            product['brand_category_ids'] = product.pop('original_category_ids')
    from build_catalog import brand_id
    result = deepcopy(snapshot)
    source = result['source']; root = SITES[source][1]
    nodes = {node['id']: node for node in result['categories']}
    if source == 'ldnet':
        from ldnet_identity import classify, revision
        for product in result['products'].values():
            classify(product, nodes)
        result['brand_classification_revision'] = revision()
    if source in WHOLE_SITE:
        categories={}
        for product in result['products'].values():
            bid=brand_id(product['brand']);memberships=product['brand_category_ids']
            product['original_category_ids']=list(memberships)
            required=set()
            for cid in memberships:
                cursor=cid;seen=set()
                while cursor!=root:
                    if cursor in seen or cursor not in nodes:raise ValueError('Invalid whole-site source ancestry')
                    seen.add(cursor);required.add(cursor);cursor=nodes[cursor]['parent_id']
            for cid in sorted(required):
                node=nodes[cid];key=bid+':'+cid
                categories[key]={'id':key,'name':node['name'],'brand':product['brand'],
                    'parent_id':bid+':'+node['parent_id'] if node['parent_id']!=root else None,
                    'source_category_id':cid}
            product['brand_category_ids']=[bid+':'+cid for cid in memberships]
        result.update(original_categories=result['categories'],categories=list(categories.values()),
            normalized_for_shop=True,scope='all',catalogue_complete=True,candidate_sha256=digest(snapshot))
        validate_candidate(result)
        return result
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
