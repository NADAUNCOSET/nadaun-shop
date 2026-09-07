"""Owner's shop shipping policy; supplier shipping terms remain source data."""
import re
import unicodedata

FEES = {'standard': 4500, 'heavy_stand': 7000}
HEAVY = re.compile(
    r'\bc\s*[+\-]?\s*(?:stand|스탠드)|씨\s*스탠드|센[츄튜]리|'
    r'(?:콤보|롤러|윈드\s*업|헤비\s*듀티).*스탠드|'
    r'(?:combo|roller|wind[\s-]*up|heavy[\s-]*duty|steel\s+senior).*stand', re.I)
ACCESSORY = re.compile(
    r'\b(?:wheels?|case|bag|extension)\b|stand\s+(?:column|base)(?:\s|\(|$)|'
    r'스탠드용|스탠드봉|보관|거치대|트레이|바퀴|어댑터|미니|'
    r'\bmini\b|\bVL-(?:033B?|40DGA|20GA|40GA)\b', re.I)


def shipping_class(product, override=None):
    if product.get('kind') != 'purchase':
        return None
    if override is not None:
        if override not in FEES:
            raise ValueError('Unknown shipping class for ' + product['id'])
        return override
    name = unicodedata.normalize('NFKC', product['name'])
    return 'heavy_stand' if HEAVY.search(name) and not ACCESSORY.search(name) else 'standard'
