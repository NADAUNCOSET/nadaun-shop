"""Publish verified, authorized AVX brands while holding unresolved overlaps."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit,parse_qs
from brand_source_policy import inventory,selections,supplemental_source_approved,POLICY
from build_catalog import brand_id


def policy_fingerprint():return hashlib.sha256(POLICY.read_bytes()).hexdigest()


def partition(snapshot):
    def terminal_hidden(p):
        evidence=p.get('source_hidden_evidence',{});url=urlsplit(evidence.get('url',''))
        return (p.get('detail_status')=='source_hidden' and p.get('supplier_status')=='unlisted'
            and p.get('content_issues')==['source_hidden_product'] and p.get('price') is None and p.get('sale_price') is None
            and p.get('source')=='avx' and p.get('id')=='avx-'+p.get('source_id','')
            and evidence.get('url')==p.get('source_url') and url.hostname=='www.avx.co.kr'
            and url.scheme=='https' and evidence.get('message')=='미노출 상품 입니다.'
            and url.path=='/goods/view' and parse_qs(url.query).get('no')==[p.get('source_id')]
            and re.fullmatch(r'[a-f0-9]{64}',evidence.get('html_sha256','')) is not None)
    if (snapshot.get('source')!='avx' or snapshot.get('scope')!='all' or
        not snapshot.get('complete') or not snapshot.get('catalogue_complete') or
        snapshot.get('coverage')!={'expected':snapshot.get('product_count'),'unique':len(snapshot.get('products',{}))} or
        snapshot.get('product_count')!=len(snapshot.get('products',{})) or
        any(p.get('detail_status')!='verified' and not terminal_hidden(p) for p in snapshot['products'].values())):
        raise ValueError('AVX publication requires a complete reconciled full-source candidate')
    chosen=selections();counts=inventory(snapshot);supplemental=supplemental_source_approved('avx')
    accepted={};held={};excluded={};brand_held={};content_review={}
    for pid,p in snapshot['products'].items():
        bid=brand_id(p['brand']);choice=chosen.get(bid,{})
        allowed=choice.get('sources') or [choice.get('source')]
        if choice and 'avx' not in allowed and (choice.get('exclusive') or not supplemental):excluded[pid]=bid
        elif not supplemental and not choice and len(counts.get(bid,{}))>1:
            held[pid]=bid;brand_held[pid]=bid
        elif p.get('content_issues') or p.get('content_status')=='review_required':
            held[pid]=bid;content_review[pid]=p.get('content_issues') or ['source_content_review']
        else:accepted[pid]=deepcopy(p)
    decisions={'policy_sha256':policy_fingerprint(),'source_product_count':snapshot['product_count'],
        'accepted_ids':sorted(accepted),'held_ids':held,'excluded_ids':excluded,
        'pending_brands':dict(sorted(Counter(brand_held.values()).items())),
        'content_review_ids':content_review,
        'owner_excluded_brands':dict(sorted(Counter(excluded.values()).items()))}
    required={cid for p in accepted.values() for cid in p.get('brand_category_ids',[])}
    by_id={c['id']:c for c in snapshot['categories']}
    for cid in list(required):
        current=cid;seen=set()
        while current:
            if current in seen or current not in by_id:raise ValueError('Invalid AVX category ancestry: '+cid)
            seen.add(current);required.add(current);current=by_id[current]['parent_id']
    public={**deepcopy(snapshot),'scope':'approved-brands','catalogue_complete':False,
        'products':accepted,'product_count':len(accepted),
        'categories':[deepcopy(c) for c in snapshot['categories'] if c['id'] in required],
        'brands':sorted({p['brand'] for p in accepted.values()}),
        'coverage':{'expected':len(accepted),'unique':len(accepted)},
        'publication':{'full_collection_verified':True,'source_product_count':snapshot['product_count'],
            'accepted_product_count':len(accepted),'pending_product_count':len(held),
            'owner_excluded_product_count':len(excluded),'pending_brand_count':len(decisions['pending_brands']),
            'source_hidden_product_count':sum(p.get('detail_status')=='source_hidden' for p in snapshot['products'].values()),
            'source_verified_detail_count':sum(p.get('detail_status')=='verified' for p in snapshot['products'].values()),
            'pending_content_product_count':len(content_review),
            'policy_sha256':decisions['policy_sha256']}}
    return public,decisions
