"""Brand-scoped catalogue identities and an auditable, repeatable merge pass.

Source records are never deleted. Price is not an identity, and shared images
or a camera compatibility number alone are never sufficient to merge products.
"""
from collections import defaultdict, Counter
from copy import deepcopy
from datetime import datetime
import re
import unicodedata


def text(value):
    return unicodedata.normalize('NFKC', str(value or '')).casefold().translate(
        str.maketrans({'–':'-', '—':'-', '−':'-', '\u200b':'', '\ufeff':''}))


def name_key(product, brand=None):
    value = text(product['name'])
    if brand:
        aliases = sorted(set([brand['name'], *brand.get('aliases', [])]), key=len, reverse=True)
        for alias in aliases:
            value = re.sub(r'(?<![a-z0-9])'+re.escape(text(alias))+r'(?![a-z0-9])', ' ', value)
    # Keep signs, decimals, slashes and model suffixes: 1.4 is not 14,
    # 70-200 is not 70200, and a kit with + components is not a bare product.
    return re.sub(r'[\s_\[\](),]+', '', value)


def model_key(product):
    if product['kind'] != 'purchase':
        return None
    value = text(product['name']).upper()
    brand = product['brand_id']
    patterns = {
        'smallrig': r'(?<![A-Z0-9])(?:SR)?(\d{3,4}[A-Z]?)(?![A-Z0-9])',
        'tilta': r'(?<![A-Z0-9])((?:TA|ES|WLC|MB|UBP|TGA|TT|HDA|GSS|TAM)-[A-Z0-9]+(?:-[A-Z0-9]+)*)(?![A-Z0-9])',
        'pgytech': r'(?<![A-Z0-9-])(P-[A-Z0-9]+-\d{3}[A-Z]?(?:-[A-Z0-9]+)*)(?![A-Z0-9-])',
        'fxlion': r'(?<![A-Z0-9])((?:BP|PL|FX|BM)-[A-Z0-9]+(?:-[A-Z0-9]+)*)(?![A-Z0-9])',
    }
    if brand not in patterns:
        return None
    tokens = set(re.findall(patterns[brand], value))
    return next(iter(tokens)) if len(tokens) == 1 else None


def option_key(detail):
    # Ignore differences in old prices/IDs but preserve selectable sizes/colors.
    return tuple(sorted(set(re.sub(r'[^\w.+-]', '', text(o.get('name')))
                            for o in detail.get('options', []) if o.get('name'))))


def variants(product):
    name = text(product['name'])
    name = re.sub(r'black\s*mamba|블랙\s*맘바', '', name)
    colors = {'black':r'\bblack\b|블랙|검정', 'white':r'\bwhite\b|화이트|흰색',
              'gray':r'\bgr[ae]y\b|그레이|회색', 'silver':r'\bsilver\b|실버|은색',
              'red':r'\bred\b|레드|빨강', 'blue':r'\bblue\b|블루|파랑',
              'green':r'\bgreen\b|그린|초록', 'beige':r'\bbeige\b|베이지',
              'ivory':r'\bivory\b|아이보리', 'brown':r'\bbrown\b|브라운|갈색'}
    found = frozenset(c for c, regex in colors.items() if re.search(regex, name))
    quantities = tuple(sorted(set(re.findall(r'(?<![\d.])(\d+)\s*(?:개|pcs?\b|ea\b)', name))))
    condition = tuple(s for s in ('중고','리퍼','벌크','전시품','박스x') if s in name)
    return found, quantities, condition


def conflict(a, b, details):
    if (a['brand_id'],a['kind']) != (b['brand_id'],b['kind']):
        return 'different_brand_or_purchase_type'
    if any(details.get(p['id'],{}).get('options_require_confirmation') for p in (a,b)):
        return 'unverified_option_equivalence'
    av, bv = variants(a), variants(b)
    if av[0] and bv[0] and av[0] != bv[0]:
        return 'different_color'
    if av[1] != bv[1] and (any(int(q)>1 for q in av[1]+bv[1])):
        return 'different_quantity'
    if av[2] != bv[2]:
        return 'different_condition'
    if a['brand_id'] == 'fxlion':
        bundle = lambda p: bool(re.search(r'세트|키트|\bkit\b|\+', text(p['name'])))
        if bundle(a) != bundle(b):
            return 'different_bundle'
    ao, bo = option_key(details.get(a['id'],{})), option_key(details.get(b['id'],{}))
    if ao != bo and (ao or bo):
        return 'different_options'
    return None


def primary_key(p):
    source = p.get('source') or p['id'].split('-',1)[0]
    value = p.get('source_modified_at')
    try:
        modified = float(value) if isinstance(value,(int,float)) else datetime.fromisoformat(value).timestamp()
    except (TypeError,ValueError):
        modified = 0
    sid = str(p.get('source_id') or p['id'].split('-',1)[1])
    return (0 if p.get('status')=='sale' else 1,
            {'smartstore':0,'imweb':1,'kpp':2}.get(source,3), -modified,
            -int(sid) if sid.isdigit() else 0, p['id'])


def deduplicate(products, details, brands, rules=None):
    rules = rules or {}
    corrections = []
    for pid, rule in rules.get('corrections', {}).items():
        p = products.get(pid)
        if not p:
            continue
        expected = rule.get('expected_name')
        if expected and text(p['name']) not in (text(expected),text(rule.get('name'))):
            raise RuntimeError('Reviewed product title changed; recheck identity: '+pid)
        before = p['name']
        for key in ('name','hidden','status'):
            if key in rule:
                p[key] = rule[key]
        corrections.append({'id':pid,'before':before,'after':p['name'],'hidden':p.get('hidden',False),
                            'reason':rule['reason'],'evidence':rule.get('evidence',[])})

    active = {pid:p for pid,p in products.items() if not p.get('hidden')}
    identities = defaultdict(list)
    for pid,p in active.items():
        prefix = (p['brand_id'],p['kind'])
        identities[(*prefix,'name',name_key(p,brands.get(p['brand_id'])))].append(pid)
        sku = model_key(p)
        if sku:
            identities[(*prefix,'model',sku)].append(pid)
    parent = {pid:pid for pid in active}
    members = {pid:{pid} for pid in active}
    evidence = defaultdict(set)
    rejected = []

    def find(pid):
        while parent[pid] != pid:
            parent[pid] = parent[parent[pid]]
            pid = parent[pid]
        return pid

    for identity, ids in sorted(identities.items()):
        if len(ids)<2:
            continue
        ids = sorted(ids)
        for i,left in enumerate(ids):
            for right in ids[i+1:]:
                ar,br = find(left),find(right)
                if ar == br:
                    evidence[ar].add(identity[2]+':'+identity[3]);continue
                reason = next((reason for a in members[ar] for b in members[br]
                               if (reason:=conflict(active[a],active[b],details))),None)
                if reason:
                    rejected.append({'ids':[left,right],'identity':identity[2]+':'+identity[3],'reason':reason})
                    continue
                parent[br] = ar
                members[ar] |= members.pop(br)
                evidence[ar] |= evidence.pop(br,set()) | {identity[2]+':'+identity[3]}

    redirects, groups = {}, []
    for representative,ids in sorted(members.items()):
        if len(ids)<2:
            continue
        ordered = sorted((active[pid] for pid in ids),key=primary_key)
        primary = ordered[0]
        pid = primary['id']
        groups.append({'brand_id':primary['brand_id'],'kind':primary['kind'],'primary_id':pid,
                       'evidence':sorted(evidence[find(pid)]),
                       'members':[{'id':p['id'],'name':p['name'],'price':p.get('sale_price'),
                                   'source':p.get('source'),'url':p['source_url']} for p in ordered]})
        for duplicate in ordered[1:]:
            did = duplicate['id']
            for field in ('category_ids','type_ids','promotion_ids'):
                primary[field] = list(dict.fromkeys(primary.get(field,[])+duplicate.get(field,[])))
            seen = {o['id'] for o in primary['offers']}
            primary['offers'] += [deepcopy(o) for o in duplicate['offers'] if o['id'] not in seen]
            if not primary.get('supplier_status'):
                primary['supplier_status'] = duplicate.get('supplier_status')
            for kind in ('main','detail'):
                if not details[pid]['images'].get(kind):
                    details[pid]['images'][kind] = deepcopy(details[did]['images'].get(kind,[]))
            redirects[did] = pid
            del products[did]
    audit = {'schema_version':1,'brands_checked':len(brands),'input_count':len(active),
             'duplicate_group_count':len(groups),'duplicate_entries_removed':len(redirects),
             'by_brand':dict(Counter(g['brand_id'] for g in groups)),
             'groups':groups,'kept_distinct':rejected,'corrections':corrections}
    return redirects, audit
