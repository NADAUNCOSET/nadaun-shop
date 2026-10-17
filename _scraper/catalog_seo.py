"""Page intent and discovery terms grounded in NADAUN's actual services.

These are relevance choices, not measured search-volume rankings. Keep location
terms on the rental/studio service pages rather than every purchase product.
"""
import json
import re
import xml.etree.ElementTree as ET
import html

SITE = 'https://shop.nadaun.co/'
PAGE_METADATA = {
    'index.html': ('나다운 스페이스 | 영등포 촬영장비 구매·렌탈',
                   '서울 영등포 나다운 스페이스. 카메라·렌즈·조명 구매와 장비 렌탈, 자연광·호리존 스튜디오 대여, 기프트·굿즈를 안내합니다.'),
    'catalog.html': ('카메라·렌즈·조명 구매 | 나다운 스페이스',
                     '나다운 스페이스의 촬영장비 쇼핑몰. 카메라·렌즈·조명·삼각대와 촬영 액세서리를 브랜드·제품 종류로 찾고 구성과 재고를 상담하세요.'),
    'catalog_category.html': ('촬영장비 종류별 찾기 | 나다운 스페이스',
                              '카메라, 렌즈, 촬영조명, 삼각대와 액세서리를 제품 종류별로 확인하세요. 구매 상품과 장비 렌탈을 구분해 안내합니다.'),
    'brands.html': ('촬영장비 브랜드 찾기 | 나다운 스페이스',
                    'DJI·SmallRig·Leofoto 등 촬영장비 브랜드별 상품과 옵션을 확인하세요. 나다운 스페이스에서 구매·렌탈 상담을 안내합니다.'),
    'rental-guide.html': ('영등포 렌탈샵 · 카메라·렌즈·조명 대여 | 나다운 스페이스',
                         '서울 영등포 나다운 스페이스의 촬영장비 렌탈. 카메라·렌즈·조명·모니터의 대여 구성, 최대 2주 이용과 픽업·반납을 안내합니다.'),
    'studio.html': ('영등포 자연광·호리존 스튜디오 대여 | 나다운 스튜디오',
                    '서울 영등포 나다운 스튜디오. 자연광·호리존·전동 배경지와 룩북·제품 촬영 공간, 시설 및 예약 방법을 안내합니다.'),
    'about.html': ('나다운 스페이스 소개 | 영등포 촬영장비·스튜디오',
                   '레인보우베네가 운영하는 나다운 스페이스. 영등포 촬영장비 구매·렌탈, 스튜디오 대여와 기프트·굿즈를 안내합니다.'),
    'services.html': ('구매·장비 렌탈 이용안내 | 나다운 스페이스',
                      '나다운 스페이스의 촬영장비 구매·렌탈 방법과 영등포 픽업·반납, 기프트 견적, 장비 협찬·사진영상 제작 문의를 안내합니다.'),
    'gifts.html': ('기업 선물·판촉물·브랜드 굿즈 | 나다운 기프트',
                   '나다운 기프트의 기업 선물, 판촉물과 브랜드 굿즈. 수량·인쇄·포장 조건을 비교하고 재고·제작 일정과 최종 견적을 상담하세요.'),
}


def page_metadata(filename, title, description):
    return PAGE_METADATA.get(filename, (title, description))


def page_structured_data(filename, title, description, canonical, *, brand=False):
    """Describe indexable pages, without asserting inventory, ratings or rank."""
    if filename in {'item.html', 'gift-item.html', 'cart.html', 'checkout.html',
                    'orders.html', 'admin.html', 'payment-test.html', 'search.html', 'account.html', 'test-shop.html', 'test-admin.html', 'members-admin.html'}:
        # Product/search endpoints supply their own request-specific metadata.
        return ''
    page_type = 'CollectionPage' if brand or filename in {
        'catalog.html', 'catalog_category.html', 'brands.html', 'gifts.html'} else 'WebPage'
    page = {'@type': page_type, '@id': canonical+'#webpage', 'url': canonical,
            'name': title, 'description': description, 'inLanguage': 'ko-KR',
            'isPartOf': {'@id': SITE+'#website'}}
    graph = [page]
    if filename == 'index.html':
        page['about']={'@id': SITE+'#store'}
        page['relatedLink']=['https://collective.nadaun.co/', 'https://photo.nadaun.co/',
                             'https://video.nadaun.co/', 'https://smartstore.naver.com/rainbowbene',
                             SITE+'services-guide.html']
        graph.append({'@type': 'WebSite', '@id': SITE+'#website', 'url': SITE,
                      'name': '나다운 스페이스', 'alternateName': ['나다운 샵', 'NADAUN SPACE', 'NADAUN SHOP'],
                      'inLanguage': 'ko-KR', 'publisher': {'@id': SITE+'#store'}})
    else:
        breadcrumb = {'@type': 'BreadcrumbList', '@id': canonical+'#breadcrumb',
                      'itemListElement': [
                          {'@type': 'ListItem', 'position': 1, 'name': '나다운 스페이스', 'item': SITE},
                          {'@type': 'ListItem', 'position': 2, 'name': title.split(' | ')[0], 'item': canonical}]}
        graph.append(breadcrumb)
        page['breadcrumb'] = {'@id': breadcrumb['@id']}
    # Escape script-closing HTML even if a future supplier brand contains it.
    data = json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False,
                      separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return '<script type="application/ld+json">'+data+'</script>'

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
    (r'모니터|monitor|디스플레이|display', ['모니터']),
    (r'프롬프터|prompter', ['프롬프터']),
]


def storage_search_terms(name):
    """Connect source abbreviations to customer queries without mixing A/B cards."""
    match = re.search(r'(?:\bCFE|\bCF\s*EXPRESS|CF\s*익스프레스)(?:\s*[24]\.0)?\s*[- ]?\s*(?:TYPE\s*)?([AB])(?:\s*타입|\b)', name, re.I)
    if not match:
        return []
    card_type = match[1].upper()
    return [f'CFexpress Type {card_type}', f'CFexpress {card_type}',
            f'CFE-{card_type}', f'CF익스프레스 {card_type}타입',
            f'씨에프익스프레스 {card_type}']


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
                               *storage_search_terms(product['name']),
                               *(['촬영장비 대여', '장비 대여'] if product['kind'] == 'rental' else [])]))
    if product.get('release_status') == 'coming_soon':
        terms.extend(['출시 예정', '가격 미공개'])
        suffix = ' 구매 안내. 출시 예정 · 가격 미공개. 출시 일정 상담.'
    elif product['kind'] == 'rental':
        is_studio = product.get('rental', {}).get('service') == 'studio'
        terms.extend(['나다운 스튜디오', '영등포 스튜디오 대여'] if is_studio else
                     ['나다운 스페이스', '영등포 렌탈샵', '영등포 촬영장비 대여'])
        suffix = (' 렌탈·대여 안내. 영등포 나다운 스튜디오 공간·일정 상담.' if is_studio else
                  ' 렌탈·대여 안내. 영등포 나다운 스페이스에서 구성·일정 상담.')
    else:
        suffix = ' 구매 안내. 나다운 스페이스에서 옵션·재고·납기 상담.'
    return {'tags': tags, 'search_terms': terms, 'categories': leaves,
            'description': product['name'][:80-len(suffix)] + suffix}


def root_sitemap(gift_index):
    """A single submission covers equipment and all gift shards, without nesting indexes."""
    namespace = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
    root = ET.fromstring(gift_index)
    if root.tag != namespace+'sitemapindex':
        raise ValueError('Gift sitemap index expected')
    parts = [node.text for node in root.iter(namespace+'loc')]
    if not parts or len(parts) != len(set(parts)) or any(
            not re.fullmatch(r'https://shop\.nadaun\.co/gift-sitemap-[1-9][0-9]*\.xml', value or '')
            for value in parts):
        raise ValueError('Gift sitemap shard URL is not canonical')
    maps = [SITE+'catalog-sitemap.xml', *parts]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+
            ''.join('<sitemap><loc>'+html.escape(url)+'</loc></sitemap>' for url in maps)+
            '</sitemapindex>\n')
