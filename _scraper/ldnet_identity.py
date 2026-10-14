"""LDNET is a supplier: resolve consumer brands from its catalogue evidence.

Keep the supplier's manufacturer value separately. A compatible device brand
inside a title is never sufficient; only a named brand menu, an explicit title
prefix, or a reviewed supplier-owned detail-image directory is used.
"""
import hashlib
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


SUPPLIER_NAMES = {'(주)엘디네트웍스', '엘디네트웍스', '엘디네트웍스(주)', 'ldnet'}
BRANDS = {
    '애니포트': ('애니포트', 'anyport'),
    'IRIVER': ('아이리버', 'iriver'),
    '엘디엘마운트': ('엘디엘마운트', '엘디 엘마운트', '엘마운트', 'ldl-mount'),
    'NEXT': ('이지넷유비쿼터스', '넥스트유', 'nextu', 'next'),
    'ATEN': ('aten',), 'APC': ('apc스토어', 'apc'),
    'TP-LINK': ('tp-link', 'tplink'), 'SOLTECH': ('soltech',),
    'HPE Aruba': ('hpe aruba',), 'HPE': ('hpe',),
    '넷기어': ('netgear', '넷기어'), '넷메이트': ('netmate', '넷메이트'),
    '보쉬': ('bosch', '보쉬'), 'DEWALT': ('dewalt', '디월트'),
    'LS전선': ('ls전선',), 'PHOENIXCONTACT': ('phoenixcontact',),
    '유그린': ('유그린', 'ugreen'), '인네트워크': ('인네트워크',),
    '벤션': ('벤션', 'vention'), '스타링크': ('스타링크',),
    '랜스타': ('랜스타',), '유니콘': ('유니콘',),
    '스마트키퍼': ('스마트키퍼',), '지데빌': ('지데빌', 'gdevil'),
    '지니큐': ('지니큐', 'ziniq'), 'UIOT': ('유아이오티', 'uiot'),
    'Xtreamer': ('엑스트리머', 'xtreamer'),
    '시스템베이스': ('시스템베이스',), 'MOXA': ('moxa',),
    'LUGBOX': ('러그박스', 'lugbox'), '파워랜': ('파워랜',),
    '이가몰드': ('이가몰드',), '진흥전기': ('진흥전기',),
    '디옵텍': ('디옵텍',), '신성전기산업': ('신성전기산업',),
    '미피': ('미피',), 'ESSAGER': ('essager',),
    'SG정보': ('sg정보', '에스지'), '대한전선': ('대한전선',),
    'JMIT': ('jmit',), '전오전기': ('전오전기',),
    'ZyXEL': ('zyxel',), 'REXTRON': ('rextron',),
    '가온전선': ('가온전선',), '디포그': ('디포그',),
    '네라네트웍': ('네라네트웍',), 'HANLONG': ('hanlong',),
    '대은전자': ('대은전자',), '디포텍': ('디포텍',),
    'Google': ('구글', 'google'), 'hohem': ('hohem',),
    'PROKIT': ('프로킷', 'prokit'), 'COMMSCOPE': ('commscope', '콤스코프'),
    '포미니': ('포미니',), '오스템': ('오스템랩', '오스템'),
    '포인트탭': ('포인트탭',), '레벤트': ('레벤트',),
}
ALIASES = {alias.casefold(): brand for brand, aliases in BRANDS.items() for alias in aliases}
TITLE_PREFIXES = sorted(ALIASES, key=len, reverse=True)


def revision():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def resolve(product, nodes):
    declared = product.get('source_manufacturer', product.get('brand', ''))
    name = product['name'].strip()
    memberships = product.get('original_category_ids', product.get('brand_category_ids', []))
    # Permit a model bracket before a written brand, but never scan arbitrary
    # compatibility text such as "LG 삼성호환" for manufacturer names.
    prefixes = [name.lstrip('[')]
    bracket = re.match(r'^\[[^\]]+\]\s*(.+)', name)
    if bracket:
        prefixes.append(bracket[1])
    for prefix in prefixes:
        for alias in TITLE_PREFIXES:
            if re.match(re.escape(alias) + r'(?=$|[\s\]/,(-])', prefix, re.I):
                return ALIASES[alias], {'method': 'explicit-title-brand', 'label': alias}
    # A brand menu resolves product-line names when the title does not name
    # the actual brand. Explicit MOXA/hohem titles outrank distributor menus.
    menu = {}
    for cid in memberships:
        cursor = cid; seen = set()
        while cursor in nodes and cursor not in seen:
            seen.add(cursor); node = nodes[cursor]
            if node.get('parent_id') == '581':
                menu[ALIASES.get(node['name'].casefold(), node['name'])] = cursor
            cursor = node.get('parent_id')
    if len(menu) == 1:
        brand = next(iter(menu))
        return brand, {'method': 'source-brand-category', 'category_id': menu[brand]}
    if len(menu) > 1:
        raise ValueError('Conflicting LDNET brand menus: ' + product['id'])
    # Reviewed directories on LDNET's own detail-asset host, not arbitrary
    # filenames or a model prefix. Banners alone cannot establish identity.
    folders = {'anyport': '애니포트', 'l-mount': '엘디엘마운트',
               'formini': '포미니', 'osstem': '오스템'}
    images = product.get('images', {}).get('detail', [])
    evidence = {}
    for url in images:
        parsed = urlsplit(url); parts = unquote(parsed.path).strip('/').split('/')
        if parsed.hostname != 'image.fzonesports.co.kr' or len(parts) < 2:
            continue
        if re.search(r'top|banner|footer|notice|delivery', parts[-1], re.I):
            continue
        if parts[0].casefold() in folders:
            evidence[folders[parts[0].casefold()]] = url
    if len(evidence) == 1:
        brand = next(iter(evidence))
        return brand, {'method': 'supplier-brand-detail-directory', 'url': evidence[brand]}
    if declared.strip().casefold() not in SUPPLIER_NAMES and declared.strip():
        return ALIASES.get(declared.casefold(), declared), {'method': 'declared-brand'}
    if '26' in memberships and re.match(r'^\[?(?:LD(?:[-\s\]])|엘디네트웍스)', name, re.I):
        return 'LD', {'method': 'explicit-rack-brand', 'category_id': '26'}
    # A product without identifiable brand evidence remains available in its
    # actual product categories, never under the supplier company as a brand.
    return '기타 브랜드', {'method': 'brand-not-specified'}


def classify(product, nodes):
    product.setdefault('source_manufacturer', product['brand'])
    product['brand'], product['brand_evidence'] = resolve(product, nodes)


# Used only when the supplier lists an item solely inside a brand shop and
# supplies no product-type membership. These explicit nouns supplement the
# original menu; they never replace or fabricate a source membership.
TYPE_HINTS = [
    ('540', r'키보드|마우스|장패드|keyboard|mouse'),
    ('158', r'잠금장치|포트락|보안기|정보보안|블루라이트차단'),
    ('171', r'보조배터리'), ('172', r'충전기|충전패드'),
    ('153', r'(?:USB|C타입|타입C|멀티).*허브|도킹스테이션|멀티포트.*허브'),
    ('425', r'무선\s*랜카드'), ('424', r'유선\s*랜카드|랜어댑터|랜카드'),
    ('599', r'스위칭\s*허브|스위치\s*허브|이더넷.*스위치|스위칭허브|스위치허브'),
    ('395', r'공유기|라우터|와이파이.*확장기|와이파이.*증폭기'),
    ('396', r'액세스\s*포인트|무선\s*AP|access\s*point'),
    ('398', r'인젝터|스플리터'),
    ('92', r'시리얼\s*카드|시리얼카드|시리얼\s*확장'),
    ('98', r'디바이스\s*서버|게이트웨이|원격\s*I/O'),
    ('43', r'RS.?232|RS.?422|RS.?485|시리얼.*컨버터|SATA.*컨트롤러'),
    ('81', r'광\s*컨버터|SFP|지빅'),
    ('533', r'KVM'), ('536', r'선택기|공유\s*스위치'),
    ('484', r'HDMI.*분배기'), ('88', r'분배기'),
    ('103', r'캡[쳐처]|캡처보드|캡쳐보드'),
    ('535', r'리피터|거리연장기|HDMI.*송수신|HDMI.*수신기'),
    ('99', r'컨버터|미라캐스트|미러링|영상변환'),
    ('167', r'리더기|카드리더'),
    ('85', r'하드\s*케이스|하드케이스|외장하드'),
    ('86', r'하드.*도킹|하드복사기'),
    ('84', r'NAS|DAS|데이터\s*스토리지'),
    ('154', r'SSD|HDD'), ('157', r'블루투스.*동글|무선동글'),
    ('467', r'CCTV|IP\s*카메라|홈\s*카메라'), ('473', r'웹캠'),
    ('163', r'헤드셋|헤드폰|이어폰'), ('574', r'스피커'),
    ('575', r'마이크'), ('165', r'사운드카드'),
    ('188', r'IOT|선풍기|안마|마사지|가습기|공기청정|디지털액자|스탠드\s*조명|독서등'),
    ('458', r'HDMI.*케이블'), ('105', r'USB.*케이블'),
    ('104', r'랜케이블|랜선|UTP.*케이블'),
    ('226', r'RJ.?45|커플러'), ('134', r'패치\s*판넬|패치판넬'),
    ('225', r'랜툴|테스터기|탈피기'), ('139', r'공구|드라이버|그라인더'),
    ('100', r'젠더|변환.*어[댑뎁]터'), ('269', r'케이블'),
    ('180', r'멀티탭|콘센트|멀티플러그'), ('183', r'전원.*아[답댑]터'),
    ('258', r'스마트폰.*거치|휴대폰.*거치|태블릿.*거치'),
    ('539', r'모니터.*받침|모니터암|TV.*거치'),
    ('186', r'차량|타이어'),
]


def type_hint(name, available):
    for cid, pattern in TYPE_HINTS:
        if cid in available and re.search(pattern, name, re.I):
            return cid
    return None
