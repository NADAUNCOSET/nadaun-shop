"""SLRrent product-type hierarchy, using only our own rental inventory."""
import json
import re
from pathlib import Path
from collections import Counter

LABELS={
 '1':'시네마','10':'시네마 패키지','11':'시네마 카메라','12':'시네마 렌즈','13':'시네마 액세서리',
 '2':'카메라','21':'카메라 패키지','23':'DSLR','24':'미러리스','26':'캠코더','206':'스마트폰','25':'VR·360 카메라','27':'액션캠·포켓 카메라','28':'드론','29':'컴팩트·기타 카메라',
 '3':'렌즈','53':'렌즈 패키지','51':'DSLR 렌즈','90':'미러리스 렌즈','50':'렌즈 어댑터','91':'필터',
 '4':'조명','102':'LED 조명','401':'램프 조명','47':'스트로보·플래시','103':'조명 액세서리','104':'배경·조명 스탠드','57':'배터리·전원','105':'포토박스',
 '5':'마이크·오디오','368':'무선 마이크','54':'유선 마이크','113':'레코더·믹서','213':'붐폴','223':'무선 타임코드','114':'스피커·앰프','115':'무전기','116':'헤드폰','117':'마이크 스탠드','210':'인터컴',
 '6':'TV·디스플레이','119':'프로젝터·스크린','120':'TV','124':'캘리브레이션',
 '7':'삼각대·서포트','127':'삼각대·모노포드·헤드','132':'짐벌·스테빌라이저','133':'달리·슬라이더','134':'매트박스·팔로우포커스','135':'리그·케이지','139':'지브·크레인','140':'기타 서포트',
 '8':'촬영 액세서리','232':'프롬프터','145':'모니터·레코더·영상 송수신','146':'메모리·스토리지','46':'배터리·전원','147':'가방·케이스','56':'기타 액세서리',
 '9':'기타 장비','155':'노트북','158':'포토 프린터','159':'촬영 소품','160':'기타 장비·용품',
 '72':'시네마 필터','64':'시네마 삼각대','38':'시네마 모니터','195':'렌즈 익스텐더','66':'시네마 레코더','67':'리모트','68':'매트박스','39':'팔로우포커스','180':'무선 포커스','41':'그립 시스템','70':'배터리·충전기','220':'메모리·리더기',
 '81':'핸디캠','82':'프로페셔널 캠코더','225':'OLED TV','121':'UHD TV','122':'HD TV','199':'포터블 스크린','123':'기타 TV',
 '141':'팬','202':'스모그 머신','142':'슬레이트','171':'모니터 후드','143':'턴테이블',
 '270':'애플박스','271':'테더링','272':'카메라 플레이트','273':'사다리','274':'카트','275':'의자·테이블','276':'광학 용품',
}
TYPE_MAP={
 'camera':'2','mirrorless':'24','dslr':'23','cinema-camera':'11','camcorder':'26','compact-camera':'29','medium-camera':'medium-camera','medium-lens':'medium-lens',
 'kpp:03':'3','kpp:0310':'51','kpp:0320':'90','kpp:0350':'90','kpp:0330':'50','kpp:04':'12','kpp:0440':'195','kpp:0450':'72','kpp:0460':'13','kpp:02':'91',
 'kpp:01':'127','kpp:0610':'127','kpp:0140':'272','kpp:0150':'135','kpp:06':'135','kpp:0620':'135','kpp:0630':'134','kpp:0640':'134','kpp:06b0':'133','rig-carts':'274','jib':'139','turntable':'143','teleprompter':'232',
 'kpp:07':'4','kpp:0710':'102','flash':'47','kpp:0720':'103','light-stand':'104','background':'104','power':'46','kpp:0680':'46',
 'audio':'5','kpp:0730':'54','wireless-mic':'368','kpp:0740':'117','audio-recorder':'113','audio-mixer':'113','speakers':'114','intercom':'210','kpp:0750':'116','apple-box':'270',
 'kpp:h0':'145','kpp:c0':'27','kpp:c010':'28','kpp:c020':'27','kpp:c040':'132','kpp:0670':'132',
 'kpp:05':'147','kpp:08':'271','kpp:09':'56','storage':'146','kpp:0960':'146','other':'160','tv-display':'120','projector':'119','color':'124','print':'158','studio':'studio',
}

def build_rental_taxonomy(products,categories):
    reference=json.loads((Path(__file__).parent/'references/slrrent-categories.json').read_text())
    # Brand leaves belong in the brand filter, not the product-type menu.
    selected=[c for c in reference['categories'] if c['depth']<2 or c['parent_id'] in ('13','26','120','140','56')]
    nodes={}
    for c in selected:
        key='rent:'+c['id']
        nodes[key]={'id':key,'name':LABELS.get(c['id'],c['name']),'parent_id':'rent:'+c['parent_id'] if c['parent_id'] else None,'brand_id':None,'scope':'rental-product','source_id':c['id'],'source_name':c['name']}
    nodes['rent:studio']={'id':'rent:studio','name':'스튜디오 대여','parent_id':'rent:9','brand_id':None,'scope':'rental-product','source_id':None}
    for key,name,parent in [('medium-camera','중형 카메라','2'),('medium-lens','중형 렌즈','3')]:
        nodes['rent:'+key]={'id':'rent:'+key,'name':name,'parent_id':'rent:'+parent,'brand_id':None,'scope':'rental-product','source_id':None}
    audit=[];brand_nodes={}
    for p in products:
        if p['kind']!='rental':continue
        types=[c for c in p['type_ids'] if c.startswith('type:')]
        parents={categories[c]['parent_id'] for c in types}
        leaves=[c for c in types if c not in parents]
        destinations=[]
        for leaf in leaves:
            current=leaf
            while current:
                key=TYPE_MAP.get(current.removeprefix('type:'))
                if key:destinations.append('rent:'+key);break
                current=categories[current]['parent_id']
        name=p['name']
        if re.search(r'ARRI\s*True\s*Blue',name,re.I):destinations=['rent:401']
        if re.search(r'오즈모\s*360|osmo\s*360',name,re.I):destinations=['rent:25']
        if re.search(r'시네새들',name):destinations=['rent:140']
        if 'rent:113' in destinations and re.search(r'앰프|amplifier',name,re.I):destinations=['rent:114']
        if re.search(r'^(?:(?:CANON|캐논)\s*)+(?:RF|EF)\s*\d',name,re.I):destinations=['rent:90' if re.search('RF',name,re.I) else 'rent:51']
        if any(x in destinations for x in ('rent:11','rent:23','rent:24','rent:26')) and ('+' in name or '케이지 세트' in name):destinations.append('rent:10' if 'rent:11' in destinations else 'rent:21')
        if not destinations:destinations=['rent:160']
        assigned=[]
        for dest in dict.fromkeys(destinations):
            current=dest;path=[]
            while current:path.insert(0,current);current=nodes[current]['parent_id']
            assigned.extend(path)
        assigned=list(dict.fromkeys(assigned));p['type_ids']=list(dict.fromkeys(p['type_ids']+assigned))
        for cid in assigned:
            c=nodes[cid];bid=p['brand_id'];key='rental-brand:'+bid+':'+cid.removeprefix('rent:')
            parent='rental-brand:'+bid+':'+c['parent_id'].removeprefix('rent:') if c['parent_id'] else None
            brand_nodes[key]={'id':key,'name':c['name'],'parent_id':parent,'brand_id':bid,'scope':'rental-brand'}
            if key not in p['category_ids']:p['category_ids'].append(key)
        audit.append({'id':p['id'],'name':name,'brand_id':p['brand_id'],'types':assigned})
    return list(nodes.values())+list(brand_nodes.values()),{'product_count':len(audit),'category_count':len(nodes),'reference_categories':len(reference['categories']),'leaf_counts':dict(Counter(c for a in audit for c in a['types'])),'assignments':audit}
