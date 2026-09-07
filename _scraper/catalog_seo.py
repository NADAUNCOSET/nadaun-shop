"""Relevant discovery terms derived from real product names and source categories."""
import re

TOPICS = [
    (r'삼각대|tripod', ['삼각대', '트라이포드']),
    (r'에어\s*블로[우워]|블로어|blower', ['에어블로우', '에어블로워']),
    (r'\bV?ND[0-9/+-]*\b|엔디|중성밀도', ['ND필터', '엔디필터']),
    (r'필터|filter', ['필터']),
    (r'짐벌|gimbal|ronin|로닌', ['짐벌']),
    (r'조명|lighting|LED라이트', ['촬영조명']),
    (r'마이크|microphone|wireless mic', ['마이크']),
    (r'렌즈|lens', ['렌즈']),
    (r'드론|drone|매빅|mavic|에어3|mini 4 pro', ['드론']),
    (r'케이지|cage', ['카메라 케이지']),
    (r'모노포드|monopod', ['모노포드']),
    (r'스탠드|stand', ['스탠드']),
    (r'배터리|battery', ['배터리']),
    (r'소프트박스|softbox', ['소프트박스']),
    (r'액션\s*[캠카]|action [0-9]', ['액션캠']),
]


def product_discovery(product, brand, categories):
    rows = [categories[c] for c in product['category_ids'] if c in categories]
    parent_ids = {c['parent_id'] for c in rows}
    leaves = list(dict.fromkeys(c['name'] for c in rows if c['id'] not in parent_ids))
    source = ' '.join([product['name'], *leaves])
    topics = list(dict.fromkeys(term for pattern, terms in TOPICS
                               if re.search(pattern, source, re.I) for term in terms))
    action = '장비 렌탈' if product['kind'] == 'rental' else '제품 구매'
    tags = list(dict.fromkeys([brand['name'], action, *topics]))[:7]
    terms = list(dict.fromkeys([*tags, *leaves, *brand['aliases'],
                               *(['촬영장비 대여', '장비 대여'] if product['kind'] == 'rental' else [])]))
    suffix = ' 렌탈·대여 안내. 일정과 장비 구성을 확인하세요.' if product['kind'] == 'rental' else ' 구매 안내. 옵션과 제품 구성을 확인하세요.'
    return {'tags': tags, 'search_terms': terms, 'categories': leaves,
            'description': product['name'][:80-len(suffix)] + suffix}
