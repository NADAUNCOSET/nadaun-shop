"""Exact camera-model associations supported by supplier product titles.

Compatibility is never inferred from a lens mount, similar product, generic
camera name, description mentions, or another item in the same category.
"""
import re,unicodedata

def model(brand,code,*aliases):
    return {'id':brand+'-'+re.sub(r'[^a-z0-9]+','-',code.lower()).strip('-'),
            'brand_id':brand,'name':{'sony':'Sony','nikon':'Nikon','canon':'Canon','panasonic':'Panasonic','fujifilm':'Fujifilm','blackmagic':'Blackmagic','ricoh':'RICOH','arri':'ARRI'}[brand]+' '+code,
            'aliases':[code,*aliases]}

MODELS=[
    model('nikon','ZR'),model('nikon','Z6 III','Z6III','Z6M3'),model('nikon','Z6 II','Z6II','Z6M2'),model('nikon','Z6'),
    model('nikon','Z7 II','Z7II'),model('nikon','Z7'),model('nikon','Z8'),model('nikon','Z9'),model('nikon','Zf'),model('nikon','Zfc'),model('nikon','Z50 II','Z50II'),model('nikon','Z50'),model('nikon','Z30'),
    model('sony','FX2','ILME-FX2'),model('sony','FX3','ILME-FX3'),model('sony','FX3A','ILME-FX3A'),model('sony','FX30','ILME-FX30'),model('sony','FX6'),model('sony','FX9'),
    model('sony','A7 V','A7V','A7M5','ILCE-7M5'),model('sony','A7 IV','A7IV','A7M4','ILCE-7M4'),model('sony','A7 III','A7III','A7M3','ILCE-7M3'),model('sony','A7 II','A7II','A7M2'),
    model('sony','A7S III','A7SIII','A7S3','A7SM3','ILCE-7SM3'),model('sony','A7S II','A7SII','A7S2','A7SM2'),
    model('sony','A7R V','A7RV','A7R5','A7RM5'),model('sony','A7R IV','A7RIV','A7R4','A7RM4'),model('sony','A7R III','A7RIII','A7R3'),
    model('sony','A7C II','A7CII','A7C2','A7CM2'),model('sony','A7CR'),model('sony','A7C'),model('sony','A9 III','A9III','A9M3'),model('sony','A1 II','A1II','A1M2'),model('sony','A1'),
    model('sony','ZV-E1','ZVE1'),model('sony','ZV-E10 II','ZVE10II','ZV-E10M2'),model('sony','ZV-E10','ZVE10'),model('sony','A6700'),model('sony','A6600'),model('sony','A6400'),
    model('canon','EOS R5 II','R5 II','R5II','R5M2','EOS R5M2'),model('canon','EOS R5 C','R5 C','R5C'),model('canon','EOS R5','R5'),
    model('canon','EOS R6 III','R6 III','R6III','R6M3'),model('canon','EOS R6 II','R6 II','R6II','R6M2'),model('canon','EOS R6','R6'),
    model('canon','EOS R1','R1'),model('canon','EOS R3','R3'),model('canon','EOS R7','R7'),model('canon','EOS R8','R8'),model('canon','EOS R10','R10'),model('canon','EOS R50 V','R50 V','R50V'),model('canon','EOS R50','R50'),
    model('canon','EOS C50','C50'),model('canon','EOS C70','C70'),model('canon','EOS C80','C80'),model('canon','EOS C400','C400'),model('canon','EOS C300 Mark III','C300 Mark III','C300M3'),
    model('panasonic','LUMIX S5 IIX','S5 IIX','S5IIX','S5M2X'),model('panasonic','LUMIX S5 II','S5 II','S5II','S5M2'),model('panasonic','LUMIX S5','S5'),
    model('panasonic','LUMIX S1 II','S1 II','S1II','S1M2'),model('panasonic','LUMIX S1R II','S1R II','S1RII','S1RM2'),model('panasonic','LUMIX S1H','S1H'),
    model('panasonic','LUMIX GH7','GH7'),model('panasonic','LUMIX GH6','GH6'),model('panasonic','LUMIX GH5 II','GH5 II','GH5II','GH5M2'),model('panasonic','LUMIX GH5','GH5'),model('panasonic','LUMIX G9 II','G9 II','G9II','G9M2'),model('panasonic','LUMIX BGH1','BGH1'),model('panasonic','LUMIX BS1H','BS1H'),
    model('fujifilm','X-H2S','XH2S'),model('fujifilm','X-H2','XH2'),model('fujifilm','X-T5','XT5'),model('fujifilm','X-T4','XT4'),model('fujifilm','X-T3','XT3'),model('fujifilm','X-S20','XS20'),model('fujifilm','X-S10','XS10'),model('fujifilm','X-M5','XM5'),model('fujifilm','X100VI'),model('fujifilm','GFX100 II','GFX100II'),model('fujifilm','GFX100S II','GFX100SII'),
    model('blackmagic','PYXIS 6K','PYXIS6K'),model('blackmagic','PYXIS 12K','PYXIS12K'),model('blackmagic','Pocket Cinema Camera 4K','BMPCC 4K','BMPCC4K','포켓 4K'),model('blackmagic','Pocket Cinema Camera 6K Pro','BMPCC 6K Pro','BMPCC6KPRO','포켓 6K PRO'),model('blackmagic','Pocket Cinema Camera 6K G2','BMPCC 6K G2','BMPCC6KG2'),
    model('ricoh','GR IV HDF','GRIV HDF','GR4 HDF','GRIVHDF','GR4HDF'),model('ricoh','GR IV','GRIV','GR4'),model('ricoh','GR III HDF','GRIII HDF','GR3 HDF','GRIIIHDF','GR3HDF'),model('ricoh','GR III','GRIII','GR3'),model('ricoh','GR IIIx','GRIIIx','GR3x'),
    # Exact model labels present in the captured Wooden Camera supplier range.
    model('sony','FX5'),model('sony','BURANO'),model('sony','VENICE'),model('sony','VENICE 2','VENICE2'),model('sony','RIALTO'),
    model('canon','EOS C500','C500'),model('canon','EOS C500 Mark II','C500 Mark II','C500MKII','C500M2'),
    model('fujifilm','GFX100S'),model('fujifilm','GFX ETERNA','GFXETERNA'),model('arri','ALEXA 35','ALEXA35'),
]
CAMERA_TYPES={'type:camera','type:mirrorless','type:cinema-camera','type:dslr','type:compact-camera','type:medium-camera'}
ACCESSORY=re.compile(r'케이지|CAGE|케이블\s*클램프|그립|GRIP|플레이트|PLATE|리그|핸들|HANDLE|L[ -]?브라켓|L[ -]?BRACKET|베이스|BASEPLATE|레일|ROD|로드|보호필름|보호커버|도브테일|DOVETAIL|케이블\s*보호|쿨링|배터리\s*커버|액세서리\s*제품군|MOUNT\s*ADAPTERS?|LENS\s*SUPPORT|BRACKET',re.I)
MAKER_ALIASES={'sony':['sony','소니'],'nikon':['nikon','니콘'],'canon':['canon','캐논'],'panasonic':['panasonic','파나소닉','lumix','루믹스'],'fujifilm':['fujifilm','fuji','후지'],'blackmagic':['blackmagic','블랙매직','bmpcc'],'ricoh':['ricoh','리코'],'arri':['arri','아리']}

def normalize(value):return unicodedata.normalize('NFKC',value).upper()
def pattern(alias):
    parts=re.split(r'[\s-]+',normalize(alias))
    return re.compile(r'(?<![A-Z0-9-])'+r'[\s-]*'.join(map(re.escape,parts))+r'(?![A-Z0-9])')
PATTERNS={m['id']:[pattern(a) for a in m['aliases']] for m in MODELS}

def title_models(product):
    title=normalize(product['name']);matches=[]
    for m in MODELS:
        # Short model codes are also used for unrelated accessories. Require
        # the camera manufacturer, rather than guessing from an A1/R5/Z8 code.
        code=m['aliases'][0].removeprefix('EOS ').removeprefix('LUMIX ')
        ambiguous=m['id']=='nikon-zr' or bool(re.fullmatch(r'(?:A1|R\d+[A-Z]?|Z\d+|ZF|S\d+|C\d+)',code,re.I))
        context=product.get('brand_id')==m['brand_id'] or any(normalize(alias) in title for alias in MAKER_ALIASES[m['brand_id']]) or (m['brand_id']=='canon' and 'EOS' in title)
        if ambiguous and not context:continue
        spans=[match.span() for expression in PATTERNS[m['id']] for match in expression.finditer(title)]
        if not spans:continue
        if any(re.search(r'호환\s*(?:불가|안됨)|미지원|지원\s*불가|NOT\s+COMPATIBLE',title[max(0,a-12):b+22]) for a,b in spans):continue
        matches.append(m)
    # Remove shorter overlapping aliases (R5 in EOS R5 II, Z6 in Z6 III).
    accepted=[]
    for m in matches:
        spans=[match.span() for expression in PATTERNS[m['id']] for match in expression.finditer(title)]
        longer=[match.span() for other in matches if other!=m for expression in PATTERNS[other['id']] for match in expression.finditer(title)]
        if all(any(a<=x and y<=b and (a,b)!=(x,y) for a,b in longer) for x,y in spans):continue
        accepted.append(m)
    return accepted

def associate(products):
    registry={};audit=[]
    for p in products:
        if p.get('kind')!='purchase':continue
        matches=title_models(p)
        if not matches:continue
        own=[m for m in matches if m['brand_id']==p['brand_id']]
        is_body=bool(own and set(p.get('type_ids',[])) & CAMERA_TYPES)
        if is_body:matches=own;field='camera_model_ids';role='camera'
        elif ACCESSORY.search(p['name']) and not set(p.get('type_ids',[])) & CAMERA_TYPES:
            field='compatible_camera_model_ids';role='accessory'
        else:continue
        p[field]=[m['id'] for m in matches]
        if role=='accessory' and '제품군' in p['name']:p['compatibility_scope']='product_family'
        for m in matches:
            if m['id'] not in registry:registry[m['id']]={**m,'camera_product_ids':[],'accessory_product_ids':[]}
            registry[m['id']]['camera_product_ids' if is_body else 'accessory_product_ids'].append(p['id'])
        audit.append({'id':p['id'],'name':p['name'],'role':role,'camera_model_ids':p[field],
                      'basis':'supplier_product_title','source_urls':[o['url'] for o in p.get('offers',[])]})
    return list(registry.values()),audit

def search_terms(product,registry):
    result=[]
    for mid in product.get('camera_model_ids',[])+product.get('compatible_camera_model_ids',[]):
        m=registry[mid]
        result.extend([m['name'],*m['aliases'],*MAKER_ALIASES[m['brand_id']]])
    return list(dict.fromkeys(result))
