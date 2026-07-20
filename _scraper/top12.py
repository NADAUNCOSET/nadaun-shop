# -*- coding: utf-8 -*-
"""12 대분류(구매Shop) 재편 매핑 — 브랜드 우선 IA (2026-07-20 대표 지시).
   상단 = 12 고정 대분류. 브랜드별=대분류 안 브랜드 타일 / 제품별=대분류 안 브랜드별 제품.

   ★모델: '브랜드=하나의 대분류에 소속'. 브랜드는 전문분야가 명확해 브랜드→대분류 매핑이
     제품별 키워드분류(14,615개가 09/기타로 폴백)보다 훨씬 정확하다.
   - 실브랜드: BRAND_CAT[slug] 우선.
   - 미분류통(_misc/_custom): 브랜드 아님 → 제품별 키워드분류(top12_product)로 카테고리 분산,
     브랜드별 타일엔 미노출.
"""

# ── 12 대분류 (스크린샷 구매Shop 순서) ──
TOP = {
 "t01":"조명램프","t02":"조명 악세서리","t03":"조명 스탠드","t04":"충전기/배터리/음향",
 "t05":"촬영 용품","t06":"카메라 렌즈/필터","t07":"연결촬영시스템","t08":"배경시스템",
 "t09":"케이스/가방","t10":"카메라 악세서리/삼각대","t11":"드론/짐벌/액션캠","t12":"HK 이큅먼트",
}
TOPORDER = ["t01","t02","t03","t04","t05","t06","t07","t08","t09","t10","t11","t12"]

PSEUDO = {"_misc","_custom"}   # 브랜드 아님(미분류통) → 제품별 키워드분류

# ── 브랜드 slug → 대분류 (도메인 지식 배정, 2026-07-20) ──
BRAND_CAT = {
 # t01 조명램프
 "godox":"t01","valens":"t01","luxpad":"t01","aputure":"t01","nanlite":"t01","nanlux":"t01",
 "arri":"t01","astera":"t01","profoto":"t01","fomex":"t01","osram":"t01","broncolor":"t01",
 "harlowe":"t01","briese":"t01",
 # t02 조명 악세서리 (모디파이어)
 "aurora":"t02","peribounce":"t02","parabolix":"t02","qualite":"t02","ragplace":"t02",
 # t03 조명 스탠드 / 그립스탠드 / 카트
 "matthews":"t03","kupo":"t03","avenger":"t03","meking":"t03","rocknroller":"t03","motion9":"t03",
 # t04 충전기/배터리/음향
 "shure":"t04","sennheiser":"t04","rode":"t04","comica":"t04","vatue":"t04","cartello":"t04",
 "zoom":"t04","tascam":"t04","apogee":"t04","arturia":"t04","presonus":"t04","genelec":"t04",
 "swit":"t04","fxlion":"t04","beillen":"t04","gentree":"t04","idx":"t04","zgcine":"t04",
 "zitay":"t04","jackery":"t04","ecoflow":"t04","klotz":"t04","alvin":"t04","pashing":"t04",
 "artmu":"t04","saramonic":"t04",
 # t05 촬영 용품 (리그·케이지·매트박스·팔로우포커스·모니터·프롬프터·슬라이더·그립·출력·태블릿)
 "tilta":"t05","smallrig":"t05","falcam":"t05","ulanzi":"t05","libec":"t05","cmotion":"t05",
 "pdmovie":"t05","edicam":"t05","zeapon":"t05","panyanfilm":"t05","bon":"t05","pmi":"t05",
 "openmoon":"t05","noga":"t05","eimage":"t05","atomos":"t05","desview":"t05","elgato":"t05",
 "tvlogic":"t05","edelkrone":"t05","cartoni":"t05","sekonic":"t05","datacolor":"t05",
 "durix":"t05","hahnemuhle":"t05","epson":"t05","wacom":"t05","eizo":"t05","robocup":"t05",
 "progaffer":"t05","evoto":"t05","captureone":"t05",
 # t06 카메라 렌즈/필터 (카메라·렌즈·필터)
 "bw":"t06","leefilters":"t06","hoya":"t06","hy":"t06","nisi":"t06","prismlensfx":"t06",
 "tokina":"t06","schneider":"t06","kase":"t06","sedona":"t06","nikon":"t06","sony":"t06",
 "canon":"t06","fujifilm":"t06","panasonic":"t06","sigma":"t06","ttartisan":"t06","viltrox":"t06",
 "laowa":"t06","samyang":"t06","xeen":"t06","dzofilm":"t06","astrhori":"t06","leitz":"t06",
 "zeiss":"t06","hasselblad":"t06","ricoh":"t06","irix":"t06","typhoon":"t06","swift":"t06",
 "marshall":"t06","blackmagic":"t06",
 # t07 연결촬영시스템 (테더링·무선영상)
 "tethertools":"t07","hollyland":"t07","teradek":"t07",
 # t08 배경시스템
 "savage":"t08","superior":"t08","kumkwang":"t08",
 # t09 케이스/가방
 "pelican":"t09","tenba":"t09","skb":"t09","wotancraft":"t09","vanguard":"t09","wandrd":"t09",
 "thinktank":"t09","oberwerth":"t09","pgytech":"t09",
 # t10 카메라 악세서리/삼각대 (삼각대·헤드·플레이트·스트랩·메모리·클리닝)
 "benro":"t10","leofoto":"t10","gitzo":"t10","ifootage":"t10","manfrotto":"t10","teris":"t10",
 "shuttler":"t10","lexar":"t10","homan":"t10","novachips":"t10","visgo":"t10",
 # t11 드론/짐벌/액션캠
 "dji":"t11","hoverair":"t11","zhiyun":"t11",
}


def top12_product(dae, jung, name):
    """키워드분류(dae/jung) → 12 대분류. 브랜드 미상/미분류통용."""
    n = (name or "").lower()
    if any(w in n for w in ("배경지","배경천","배경 시스템","배경시스템","크로마키","chroma",
                             "배경 스탠드","배경롤","롤배경","muslin","시멜리스","seamless",
                             "backdrop","background support")):
        return "t08"
    if any(w in n for w in ("라이트 스탠드","라이트스탠드","light stand","c스탠드","c-스탠드",
                             "c-stand","c 스탠드","조명 스탠드","조명스탠드","붐 스탠드",
                             "boom stand","라이트스탠","스탠드암","스탠드 암")):
        return "t03"
    if dae == "07":
        return "t01" if jung == "0710" else "t02"
    if dae == "s0": return "t04"
    if dae == "00": return "t06"
    if dae in ("02","03","04"): return "t06"
    if dae == "05": return "t09"
    if dae == "01": return "t10"
    if dae in ("08","h0"): return "t07"
    if dae == "c0": return "t11"
    if dae == "06":
        if jung == "0670": return "t11"   # 짐벌
        if jung == "0680": return "t04"   # 배터리·전원
        return "t05"
    if dae == "09": return "t10"
    return "t05"


def resolve(slug, dae, jung, name):
    """제품 → (top_code, top_name). 실브랜드=BRAND_CAT 우선, 그 외=키워드분류."""
    if slug and slug not in PSEUDO and slug in BRAND_CAT:
        t = BRAND_CAT[slug]
    else:
        t = top12_product(dae, jung, name)
    return t, TOP[t]
