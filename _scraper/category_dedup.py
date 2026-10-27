"""Collapse exact brand/category paths for publication; keep source evidence private."""
from collections import defaultdict,Counter
from copy import deepcopy
import re
import unicodedata

def label(value):
    # Preserve decimal points, slashes, model suffixes and mount punctuation.
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(value)).casefold())

def project(products,categories,brands,navigation):
    original=deepcopy(categories);groups=defaultdict(list);members=defaultdict(set);rental_protected=set()
    original_memberships={p['id']:list(p.get('category_ids',[])) for p in products}
    def ancestry(cid):
        path=[];seen=set()
        while cid:
            if cid in seen or cid not in original:raise ValueError('Invalid category path: '+str(cid))
            seen.add(cid);path.insert(0,cid);cid=original[cid].get('parent_id')
        return path
    for p in products:
        for cid in set(p.get('category_ids',[])):members[cid].add(p['id'])
    for p in products:
        if p.get('kind')=='rental':
            for cid in p.get('category_ids',[])+p.get('type_ids',[])+p.get('navigation_category_ids',[]):
                if cid in original:rental_protected.update(ancestry(cid))
    for cid,c in original.items():
        bid=c.get('brand_id')
        if bid not in brands or c.get('scope')=='rental-brand' or cid.startswith(('rental-brand:','rent:','type:')):continue
        b=brands[bid];aliases={label(x) for x in [bid,b['name'],*b.get('aliases',[])]}
        key=tuple(label(original[x]['name']) for x in ancestry(cid) if label(original[x]['name']) not in aliases)
        groups[(bid,key)].append(cid)
    redirects={};merged=[];held=[]
    for (bid,key),ids in sorted(groups.items()):
        if len(ids)<2 or len({cid.split(':')[0] for cid in ids})<2:continue
        if any(a!=b and a in ancestry(b) for a in ids for b in ids):
            held.append({'brand_id':bid,'ids':ids,'reason':'ancestor_and_descendant_must_not_merge'});continue
        protected=[cid for cid in ids if cid in rental_protected]
        if len(protected)>1:
            held.append({'brand_id':bid,'ids':ids,'reason':'distinct_existing_rental_category_ids'});continue
        preferred=navigation.get('brands',{}).get(bid,{}).get('preferred_source')
        ordered=sorted(ids,key=lambda cid:(cid not in rental_protected,not (preferred and cid.startswith(preferred+':')),-len(members[cid]),len(ancestry(cid)),cid))
        target=ordered[0]
        for old in ordered[1:]:redirects[old]=target
        merged.append({'brand_id':bid,'normalized_path':list(key),'target_id':target,'source_nodes':[{'id':cid,'name':original[cid]['name'],'original_path':[original[x]['name'] for x in ancestry(cid)],'original_parent':original[cid].get('parent_id'),'product_count':len(members[cid])} for cid in ordered]})
    mapped=lambda values:list(dict.fromkeys(redirects.get(cid,cid) for cid in values))
    for p in products:
        if p.get('kind')=='rental':continue
        for field in ('category_ids','type_ids','navigation_category_ids'):
            if field in p:p[field]=mapped(p[field])
    for b in brands.values():
        for field in ('category_ids','navigation_category_ids'):
            if field in b:b[field]=mapped(b[field])
    for old in redirects:del categories[old]
    for c in categories.values():
        c['parent_id']=redirects.get(c.get('parent_id'),c.get('parent_id'))
        cursor=c['id'];seen=set()
        while cursor:
            if cursor in seen or cursor not in categories:raise ValueError('Invalid projected category tree: '+c['id'])
            seen.add(cursor);cursor=categories[cursor].get('parent_id')
    added=0;targets=set(redirects.values())
    for p in products:
        if p.get('kind')=='rental' or 'navigation_category_ids' not in p:continue
        additions=[]
        for old in original_memberships[p['id']]:
            if old not in redirects and old not in targets:continue
            cursor=redirects.get(old,old)
            if categories[cursor].get('brand_id')!=p.get('brand_id'):continue
            while cursor:
                additions.insert(0,cursor);cursor=categories[cursor].get('parent_id')
        before=len(p['navigation_category_ids']);p['navigation_category_ids']=list(dict.fromkeys(p['navigation_category_ids']+additions));added+=len(p['navigation_category_ids'])-before
    for bid,b in brands.items():
        if 'navigation_category_ids' in b:b['navigation_category_ids']=list(dict.fromkeys(b['navigation_category_ids']+[cid for p in products if p.get('kind')=='purchase' and p.get('brand_id')==bid for cid in p.get('navigation_category_ids',[])]))
    for old,target in redirects.items():
        assert old not in categories and target in categories
        assert original[old]['brand_id']==categories[target]['brand_id']
    return redirects,{'schema_version':1,'source_categories_before':len(original),'public_categories_after':len(categories),'navigation_memberships_added':added,'duplicate_groups':len(merged),'removed_category_nodes':len(redirects),'groups':merged,'held':held,'basis':'Exact normalized full brand path only; decimals/slashes/model suffixes and different parents remain distinct. Source snapshots unchanged.'}
