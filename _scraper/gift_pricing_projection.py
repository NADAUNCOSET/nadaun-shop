"""Project only observed public selling-price tiers; no supplier fields."""
import hashlib
import json
import re
from datetime import datetime


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def pricing(detail):
    options = []
    for row in detail.get('options', []):
        selection = {k: clean(row.get('selection', {}).get(k)) for k in ('color', 'size', 'printing')}
        tiers = row.get('tiers', [])
        if not tiers:
            continue
        selected = []
        for t in tiers:
            q, price = t.get('minimum_quantity'), t.get('unit_price_ex_vat')
            if type(q) is not int or not 1 <= q <= 100000 or type(price) is not int or not 1 <= price <= 100000000:
                raise ValueError('Invalid observed gift price tier')
            selected.append({'minimum_quantity': q, 'unit_price_ex_vat': price})
        selected.sort(key=lambda t: t['minimum_quantity'])
        if len({t['minimum_quantity'] for t in selected}) != len(selected):
            raise ValueError('Conflicting gift price thresholds')
        options.append({'id': digest(selection), 'label': ' / '.join(v for v in selection.values() if v) or '기본 구성', 'selection': selection, 'tiers': selected})
    if not options:
        return None
    if len({o['id'] for o in options}) != len(options):
        raise ValueError('Conflicting gift option identity')
    observed = detail.get('pricing_observed_at') or detail.get('observed_at')
    datetime.fromisoformat(observed.replace('Z', '+00:00'))
    minimum = detail.get('minimum_quantity')
    if type(minimum) is not int or not 1 <= minimum <= 100000 or str(detail.get('vat_rate')) not in ('0.1', '0.10'):
        raise ValueError('Unverified gift minimum/VAT')
    value = {'minimum_quantity': minimum, 'vat_basis_points': 1000, 'observed_at': observed,
             'options': options, 'requires_confirmation': True}
    value['revision'] = digest(value)
    return value
