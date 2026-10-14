"""Saeki's product-category evidence, with device/accessory safeguards."""
import re

EXTRA=[('film-camera','camera','필름 카메라'),('360-camera','camera','360도 카메라'),
 ('analog',None,'필름·암실·보관'),('film','analog','촬영용 필름'),('darkroom','analog','암실·현상 장비'),
 ('photo-paper','analog','인화지'),('photo-chemicals','analog','현상·인화 약품'),('film-storage','analog','필름·사진 보관용품'),
 ('bag-parts','kpp:05','가방 액세서리·칸막이'),('binoculars','kpp:00','쌍안경·단망경'),('scope','kpp:00','스코프'),
 ('general-goods',None,'생활·기념 상품'),('industrial-support','kpp:06','산업 촬영·측정 보조 장비'),('enlarger-lens','analog','암실 확대기 렌즈'),('shooting-table','kpp:06','제품 촬영 테이블')]

GROUPS={
 'mirrorless':'100101','dslr':'100100','compact-camera':'100103 100106','film-camera':'100626','360-camera':'100104',
 'cinema-camera':'100211 100212','camcorder':'100056','kpp:c010':'100754','kpp:c020':'100105',
 'kpp:0330':'100153 100154','kpp:0340':'100157 100158 100265 100997',
 'uv':'100149 100150','cpl':'100151','kpp:0220':'100278','mist':'100744','kpp:0560':'100743 100262',
 'kpp:0110':'100159 100161','kpp:0610':'100160 100227 100228','monopod':'100162','mini-tripod':'100163',
 'pan-head':'100164','ball-head':'100165','kpp:0120':'100166','video-head':'100229',
 'kpp:0140':'100169','kpp:0150':'100170','kpp:0130':'100171 100172 100173 100230',
 'equipment-bag':'100167 100606 100175 100174 100185','kpp:0920':'100168 100180 100179 100625',
 'kpp:0650':'100111','power':'100110','cable-parts':'100113','drone-parts':'100880',
 'kpp:0510':'100176','kpp:0520':'100178','sling-bag':'100177','rolling-case':'100181 100182 100183',
 'bag-parts':'100186 100187 100188 100189',
 'flash':'100107 100190','kpp:0710':'100257 100217','kpp:0720':'100109 100193 100198',
 'power-parts':'100191','light-meter':'100192','softbox':'100194 100195','reflector':'100196 100197',
 'light-stand':'100199','light-grip':'100200 100203 100208 100209','kpp:06':'100201',
 'background':'100204 100205 100206','kpp:0640':'100218','camera-rig':'100220',
 'kpp:06b0':'100221','jib':'100222','kpp:c040':'100223','switcher':'100279',
 'monitor':'100055 100112','kpp:0730':'100270','kpp:0740':'100271','kpp:0750':'100269',
 'sd-card':'100115 100258','cf-card':'100259 100260','binoculars':'100231 100256','scope':'100232','kpp:0040':'100233',
 'print':'100263','film':'100234 100235','photo-paper':'100236','photo-chemicals':'100237',
 'darkroom':'100238 100239 100240 100241 100242 100243 100245 100246 100290 100250',
 'film-storage':'100247 100248 100249 100282','industrial-support':'100501','general-goods':'100064',
}
MAPPING={cid:target for target,ids in GROUPS.items()for cid in ids.split()}


def product_types(p):
 """Use native product categories, never promotional menus as device evidence."""
 from product_taxonomy import COMPILED,camera_accessory_type
 name=p['name'];ids=p.get('source_category_ids',[]);leaf=ids[-1]if ids else ''
 brand=p.get('brand_id','')
 # Explicit model families on source promotional pages retain product purpose.
 if brand=='tethertools' and re.search(r'USB',name,re.I):return ['usb-cable']
 if brand in {'lexar','sandisk'} and re.search(r'JumpDrive|Dual Drive|메모리',name,re.I):return ['storage']
 if brand=='rodenstock' and re.search(r'RODAGON|ROGONAR',name,re.I):return ['enlarger-lens']
 if brand=='hprc' and re.fullmatch(r'HPRC\d{4}',name,re.I):return ['rolling-case']
 if brand=='zhiyun' and re.search(r'MOLUS',name,re.I):return ['continuous']
 if brand=='rycote' and re.search(r'Windjammer|STICKIES|INV USM|MINI WJ',name,re.I):return ['kpp:0740']
 if brand=='peak-design' and '앵커' in name:return ['kpp:0920']
 if brand=='cura' and re.search(r'클리너|와이퍼|오일 스프레이',name):return ['cleaning']
 if brand=='pentax' and re.search(r'PENTAX 17.*Body KIT',name,re.I):return ['film-camera']
 if re.match(r'인스탁스 미니 \d+ 패키지',name):return ['compact-camera']
 # True photographic/cinema lens paths take precedence over mount/kit words.
 for source,target in [('100025','kpp:0310'),('100026','kpp:0320'),('100027','medium-lens')]:
  if source in ids:return [target]
 if '100050'in ids and leaf!='100265':return ['kpp:04']
 # Concrete accessory nouns override coarse device source categories.
 overrides=[
  ('kpp:0340',r'body cap|ring cap|링캡'),('kpp:0650',r'hand grip|cogrip|엄지그립'),
  ('monitor-parts',r'eye\s*cup'),('power-parts',r'AC ADAPT[EO]R|DC CONNECTOR|DC 커플러'),
  ('chargers',r'충전스테이션|charging hub'),('camera-battery',r'충전지|^D-LI\d+|^DB-110$'),
  ('chargers',r'^BJ-11$|^K-BC\d+'),('kpp:0340',r'^O-LC\d|USB Dock'),
  ('kpp:0650',r'\b[LM] GRIP O-GP'),('color',r'EzyBalance|ColorReader|그레이카드'),
  ('light-meter',r'LightColor Meter'),('reflector',r'HaloCompact.*Cover'),
  ('shooting-table',r'STILL\s*LIFE TABLE'),('light-stand',r'Baby Stand'),
  ('kpp:04',r'Cinema Zoom Lenses'),('kpp:0220',r'FSND.*FILTER'),
  ('audio-adapter',r'^Audio Extension Module'),
  ('screen-protection',r'보호\s*필름|액정\s*보호|screen\s*protector'),
  ('kpp:0960',r'리더기|card\s*reader'),('chargers',r'충전기|battery\s*charger'),
  ('camera-battery',r'^(?:Thermo Smart Battery|Grip Battery)|배터리.*호환'),
  ('light-shaping',r'^(?:ARRI )?LAMP\b'),
  ('gimbal-parts',r'짐벌용.*(?:리모트|팔로우|포커스)|gimbal.*(?:remote|accessor)'),
  ('speakers',r'블루투스\s*스피커'),('kpp:0740',r'Wavo.*마운팅\s*키트'),
 ]
 for target,pattern in overrides:
  if re.search(pattern,name,re.I):return [target]
 selected=MAPPING.get(leaf)
 if selected in {'mirrorless','dslr','compact-camera','cinema-camera','camcorder'}:
  accessory=camera_accessory_type(name,p.get('brand_id',''))
  if accessory:return [accessory]
 if selected=='monitor':
  for target,pattern in [('monitor-parts',r'hood|sunshade|후드|액세서리'),('equipment-bag',r'case|bag|케이스|가방'),('hdmi-cable',r'HDMI.*cable'),('sdi-cable',r'(?:SDI|BNC).*cable')]:
   if re.search(pattern,name,re.I):return [target]
 if selected=='kpp:0710' and re.search(r'커버|디퓨저|그리드|케이스|cover|diffuser|grid|case',name,re.I):selected=None
 if selected:return [selected]
 # Source 'other', special-order and sale menus are not product types.
 for target,pattern in COMPILED:
  if pattern.search(name):return [target]
 if '100029'in ids:return ['filter-parts']
 if '100031'in ids or '100030'in ids:return ['kpp:0340']
 if '100023'in ids:return ['other']
 if '100044'in ids or '100045'in ids:return ['kpp:0720']
 if '100048'in ids or '100052'in ids:return ['light-grip' if '100048'in ids else 'camera-rig']
 if '100008'in ids:return ['analog']
 if '100009'in ids:return ['general-goods']
 return ['other']
