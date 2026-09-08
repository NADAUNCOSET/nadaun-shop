"""Image-led product-type navigation using verified catalogue membership."""
from html import escape
from urllib.parse import urlencode


PURCHASE = ['type:camera','type:kpp:0110','type:kpp:02','type:mini-tripod',
    'type:kpp:03','type:kpp:05','type:kpp:0610','type:kpp:0250','type:kpp:04',
    'type:kpp:c010','type:kpp:c040','type:wireless-mic','type:video-wireless','type:intercom','type:monitor','type:kpp:06b0','type:car-mount','type:kpp:09','type:continuous','type:tube-light','type:mini-light','type:panel-light','type:mat-light','type:kpp:0720','type:audio-mixer','type:audio-recorder','type:power-station','type:kpp:0710','type:kpp:0730','type:kpp:0680','type:kpp:0620','type:kpp:0650',
    'type:kpp:0630','type:kpp:0640','type:kpp:0660','type:kpp:0690','type:kpp:06a0',
    'type:kpp:0670','type:kpp:0140','type:rig-carts','type:kpp:08','type:kpp:h0']
RENTAL = ['rent:11','rent:24','rent:3','rent:12','rent:102','rent:47','rent:5',
    'rent:127','rent:132','rent:133','rent:28','rent:27','rent:46','rent:145',
    'rent:146','rent:135','rent:134','rent:104','rent:147','rent:56']


def galleries(products, categories):
    result = {}
    for kind, preferred in (('purchase', PURCHASE), ('rental', RENTAL)):
        rows = [p for p in products if p['kind'] == kind and p.get('listing_id',p['id']) == p['id']]
        scope = 'rental-product' if kind == 'rental' else 'product'
        nodes = {c['id']:c for c in categories if c.get('scope') == scope}
        covered = set()
        entries = []
        # Include remaining populated root groups after the prominent categories.
        for cid in list(dict.fromkeys(preferred)) + [c['id'] for c in nodes.values() if not c.get('parent_id')]:
            if cid not in nodes or cid in covered:
                continue
            members = [p for p in rows if cid in p['type_ids'] and p.get('image')]
            if not members:
                continue
            available = [p for p in members if p['status'] != 'soldout']
            photo = (available or members)[0]
            entries.append({'id':cid,'name':nodes[cid]['name'],'kind':kind,'count':len(members),
                'image':photo['image'],'product_id':photo['id'],
                'href':'/catalog.html?'+urlencode({'kind':kind,'type':cid})})
            current = nodes[cid]
            while current and current['id'] not in covered:
                covered.add(current['id'])
                current = nodes.get(current.get('parent_id'))
        result[kind] = entries
    return result


def gallery_html(entries, kind='purchase'):
    label = '렌탈 장비 종류' if kind == 'rental' else '제품 종류'
    tiles = ''.join(f'<a class="category-image-tile" href="{escape(e["href"])}"><span class="category-image"><img src="{escape(e["image"])}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer"></span><strong>{escape(e["name"])}</strong></a>' for e in entries)
    return f'<section class="category-gallery" aria-label="{label}"><div class="section-head"><div><h2>{label}로 찾기</h2><p>종류를 고르면 모든 브랜드의 해당 상품을 볼 수 있습니다.</p></div></div><nav class="category-image-grid" aria-label="{label} 선택">{tiles}</nav></section>'
