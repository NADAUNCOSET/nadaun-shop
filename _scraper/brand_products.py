"""Choose an actual, available catalogue product for each brand's image card."""
import re

PREFERRED = {
    'dji': r'Osmo Action 6|오즈모 포켓 3',
    'smallrig': r'풀.*케이지|카메라 케이지|케이지 키트',
    'leofoto': r'카본.*삼각대|삼각대.*카본',
    'tilta': r'풀 카메라 케이지|케이지 키트',
    'hoya': r'HD.*CPL|HD.*UV',
    'hy': r'RevoRing|레보링|홀더.*세트',
    'pgytech': r'백팩|원모.*가방|OneMo',
    'nanlite': r'포르자.*(300|500)|Forza.*(300|500)',
    'godox': r'AD600|AD300|AD200|ES45 Kit',
    'kupo': r'C.STAND.*KIT|씨스탠드|C스탠드',
    'aputure': r'600[dxc]|300[dxc]|MC 12-Light',
    'tokina': r'렌즈', 'ttartisan': r'50mm|35mm',
    'wandrd': r'프르브크|PRVKE', 'fxlion': r'NANO TWO|나노 투',
    'ldl-mount': r'APL-44PRO',
    'broncolor': r'Siros 400 L WiFi', 'gitzo': r'GK1555T|GT5563GS',
    'eimage': r'GH06|EG06|Tripod.*Kit|삼각대', 'manfrotto': r'MT055|삼각대',
    'sony': r'ILME-FX3|ILME-FX6', 'nikon': r'NIKON.*ZR',
    'profoto': r'A1X|Pro-B3', 'nanlux': r'Evoke5000B',
    'pmi': r'Smoke NINJA PRO', 'joby': r'GorillaPod.*5K Kit',
    'wacom': r'DTH-271', 'lee-filters': r'낱장필터',
}
ACCESSORY = re.compile(r'케이블|어댑터|플레이트|나사|교체용|센터컬럼|디퓨저|가방 휠|부품|커넥터|리모컨|배터리 커버|고무발|보호필름', re.I)


def representative(brand_id, products, preferred_id=None):
    candidates = [p for p in products if p['brand_id'] == brand_id and p.get('image')]
    if not candidates:
        raise RuntimeError('Brand has no representative product: ' + brand_id)
    pattern = PREFERRED.get(brand_id)
    def rank(p):
        return (p['id'] != preferred_id, p['status'] == 'soldout',
                not bool(pattern and re.search(pattern, p['name'], re.I)), p['kind'] == 'rental',
                bool(ACCESSORY.search(p['name'])), not p['image'].startswith('/assets/'))
    return min(candidates, key=rank)
