# -*- coding: utf-8 -*-
"""틸타 전용 카테고리 — tilta.com 구조 동일하게(대표 지정 2026-07-06).
   대 = 카메라별(cam) / 제품군(prod).  중 = 카메라브랜드 또는 제품라인.  소 = 모델/변형.
   원본 leaf category 우선, 'Special Deals'(Open Box)·빈값·Legacy 등은 제품명으로 재분류.
   규칙 순서: 제품라인 먼저(로닌·Nucleus 등 카메라토큰 포함해도 제품군으로) → 카메라브랜드."""
import re

DAE={"cam":"카메라별","prod":"제품군","deal":"특가·Open Box"}
DAE_ORDER=["cam","prod","deal"]

# ── 제품라인 규칙 (먼저). (중키, 중이름, [키워드]) ──
LINES=[
 ("khronos","스마트폰(Khronos)", ["khronos","smartphone","스마트폰","phone mount","phone bracket","phone mounting"]),
 ("ronin","DJI 로닌", ["dji ronin","for dji ronin","ring grips for dji","ronin 4d","ronin ring","ronin s","for rs","rs 2","rs 3","rs 4","rs2","rs3","for dji rs","ronin rs"]),
 ("dji_sys","DJI 포커스·트랜스미션·마빅", ["dji focus pro","for dji focus","dji transmission","for dji transmission","dji video trans","dji mavic","for dji mavic","dji remote monitor"]),
 ("nucleus","팔로우포커스(Nucleus)", ["nucleus","follow focus","focus gear ring","focus handwheel","autofocus adapter"]),
 ("mirage","매트박스(Mirage)", ["mirage","matte box","mattebox"]),
 ("illusion","필터(Illusion)", ["illusion","magnetic filter"," filters","95mm","irnd"," nd "," cpl","vnd"]),
 ("hydra","짐벌·크레인(Hydra·Float)", ["hydra","float","armorman","armor man","gimbal support","gimbal system","gimbal","camera crane","speed pan","car mounting","hermit pov","predator shock","dan ming","gravity g","stabiliz"]),
 ("tripod","삼각대", ["tripod series","tripod"]),
 ("cart","카메라 카트", ["camera cart"]),
 ("power","파워·배터리", ["power cable","power pass","power supply","dummy batter","battery plate","battery charger","charging station","camera batter","v-mount battery","gold-mount","r/s cable","misc cable","cable clamp","p-tap","d-tap","lp-e","en-el","np-f","battery"]),
 ("support","서포트·리그·그립", ["baseplate","base plate","dovetail","top plate","handle attach","top handle","side handle","wooden handle","side wooden","handgrip","hand grip","grip end","grip system"," handle","rod/rod","rod holder","rod adapter"," rod ","lens adapter support","lens support","screw","nato mount","cold shoe","articulating arm","monitor mount","monitor cage","mounting plate","accessory mounting","suction cup","boom pole","shoulder rig","shoulder mount","evf/monitor","ssd holder","ssd drive","ssd","cheese","speed rail","focus gear","rosette","cage","rig"]),
 ("design","디자인·라이프스타일", ["fe design","tilta design","camera strap","lifestyle"]),
]
# ── 카메라 브랜드 규칙 (leaf/이름에 브랜드 토큰) ──
CAMS=[
 ("sony","Sony", ["sony"," fx6"," fx3"," fx30","fx9","fs5"," a7"," a9"," a1 "," a6","burano","venice","zv-e","zv-1","fx2 ","ilce","ilme","pxw"]),
 ("canon","Canon", ["canon","powershot"]),
 ("red","RED", ["red ","komodo","v-raptor","raptor","dsmc"]),
 ("bmd","Blackmagic", ["blackmagic","bmpcc","bmcc","pyxis","ursa"]),
 ("fuji","Fujifilm", ["fujifilm","fuji"," gfx","x100vi","x-t","x-h","x-e","x-m","x-s","x100"]),
 ("pana","Panasonic", ["panasonic","lumix"," gh"," s5"," s1","bgh1","bs1h","eva1"," g9"]),
 ("nikon","Nikon", ["nikon"," zr"," z8"," z9"," z6"," z7"]),
 ("zcam","Z CAM", ["z cam","zcam","z-cam"]),
 ("arri","Arri", ["arri","alexa"]),
 ("leica","Leica", ["leica"]),
 ("sigma","Sigma", ["sigma"]),
 ("hassel","Hasselblad", ["hasselblad"]),
 ("gopro","GoPro", ["gopro","hero "]),
 ("insta","Insta360", ["insta360"]),
 ("dji_cam","DJI 오즈모·액션", ["osmo pocket","osmo action","dji action","osmo 360","dji osmo","osmo mobile"]),
]
_BRANDWORD=re.compile(r"^(sony|canon|fujifilm|panasonic|nikon|leica|sigma|hasselblad|arri|red|z\s?cam|insta360|gopro|dji)\s+",re.I)

def _clean_so(leaf):
    """카메라 소분류 표시용: 앞 브랜드 단어 제거('Sony FX6'→'FX6')."""
    s=_BRANDWORD.sub("",leaf).strip()
    return s or leaf

def _match(text, rules):
    t=text.lower()
    for key,name,kws in rules:
        for k in kws:
            if k in t: return key,name
    return None

_GENERIC_LEAF={"special deals","","legacy","misc. parts","misc cables","tilta design","fe design"}

def classify_tilta(name, category=""):
    cat=(category or "").strip()
    catl=cat.lower()
    # 1) 깨끗한 leaf(=Special Deals/빈값 아닌) → leaf로 분류. 소(小)=원본 leaf(tilta.com 컬렉션명)
    if catl not in ("special deals",""):
        m=_match(catl, LINES)
        if m: return "prod",DAE["prod"],m[0],m[1],_rawslug(cat), _pretty_leaf(cat,m[1])
        c=_match(catl, CAMS)
        if c: return "cam",DAE["cam"],c[0],c[1],_slug_so(cat), _clean_so(cat)
    # 2) Special Deals/빈값 → 특가·Open Box 대분류. 중=감지된 카메라/제품라인(하위필터용)
    txt=(name or "")
    c=_match(txt, CAMS)
    if c: return "deal",DAE["deal"],c[0],c[1],"",""
    m=_match(txt, LINES)
    if m: return "deal",DAE["deal"],m[0],m[1],"",""
    # 3) 폴백
    return "deal",DAE["deal"],"etc","기타","",""

def _slug_so(leaf):
    return re.sub(r"[^a-z0-9]+","_",_clean_so(leaf).lower()).strip("_") or "etc"

def _rawslug(s):
    return re.sub(r"[^a-z0-9]+","_",(s or "").lower()).strip("_") or "etc"

# 소(小) 표시명: 중분류와 중복되는 꼬리말 제거해 짧게
_SO_STRIP=[" Wireless Lens Control System"," Handheld Gimbal Support System"," Gimbal Support System",
           " Portable Camera Crane"," Matte Box"," Car Mounting System"," Support System"," Series"]
def _pretty_leaf(leaf, jung_name):
    s=leaf
    for suf in _SO_STRIP:
        if s.endswith(suf) and len(s)>len(suf)+2: s=s[:-len(suf)]
    return s.strip() or leaf
