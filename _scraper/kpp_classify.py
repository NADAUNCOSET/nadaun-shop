# -*- coding: utf-8 -*-
"""KPP(kppkpp.co.kr) 대>중>소 카테고리 분류기 — shop.nadaun.co 표준(SoT: data/taxonomy_kpp.md).

제품명(+원본 category) 키워드 기반. RULES를 위에서부터 첫 매칭(specific→general 순).
반환: (dae_code, dae_name, jung_code, jung_name).

KPP 원표준 + 데이터 현실 확장 2개:
  00 카메라·바디  (KPP엔 대분류 없음 — clmedia 카메라 바디 56개용)
  06c0 모니터·뷰파인더  (필드 모니터 125개 — 06 영상장비 하위 확장)
확장은 taxonomy_kpp.md에 명시.
"""
import re

# ── 대분류 표시명 ──
DAE = {
    "00": "카메라·바디",
    "01": "삼각대",
    "02": "필터",
    "03": "카메라렌즈",
    "04": "시네마렌즈",
    "05": "카메라가방",
    "06": "영상장비",
    "07": "조명",
    "s0": "사운드·마이크",
    "08": "테더툴스",
    "09": "액세서리",
    "c0": "드론·액션캠",
    "h0": "영상송수신기",
}
# 대분류 표시 순서(SoT 트리 순 + 확장은 관련 위치)
DAE_ORDER = ["00","01","02","03","04","05","06","07","s0","h0","08","09","c0"]

# ── 중분류 표시명 ──
JUNG = {
    "0000":"카메라 바디",
    "0110":"삼각대","0120":"삼각대헤드","0130":"삼각대 액세서리","0140":"플레이트","0150":"클램프","0160":"기타",
    "0210":"UV·CPL","0220":"ND","0230":"효과필터","0240":"사각필터","0250":"마그네틱시스템","0260":"클립인필터","0200":"기타 필터",
    "0310":"DSLR/미러리스","0330":"렌즈어댑터","0340":"렌즈 액세서리","0350":"RF","0360":"특수효과","0300":"기타 렌즈",
    "0410":"프라임","0420":"줌","0430":"매크로","0440":"익스팬더","0460":"시네렌즈 액세서리","0400":"기타 시네렌즈",
    "0510":"백팩","0520":"숄더백","0530":"케이스","0550":"테크파우치","0560":"렌즈·필터케이스","0500":"기타 가방",
    "0610":"비디오삼각대","0620":"케이지·베이스플레이트","0630":"매트박스","0640":"팔로우포커스·렌즈컨트롤",
    "0650":"핸들·그립","0660":"숄더리그","0670":"짐벌·스태빌라이저","0680":"배터리·전원","0690":"암·마운트·액세서리",
    "06a0":"스마트폰 리그","06b0":"슬라이더·달리","06c0":"모니터·뷰파인더","0600":"기타 영상장비",
    "0710":"LED·지속광","0720":"조명 액세서리","0700":"기타 조명",
    "s010":"마이크","s020":"마이크 액세서리","s030":"헤드셋·모니터링","s000":"기타 사운드",
    "0810":"테더 케이블","0800":"테더툴스",
    "0910":"카메라뱃지","0920":"스트랩","0930":"장갑","0940":"청소키트","0950":"렌즈·테크랩","0960":"리더기·저장","0900":"기타 액세서리",
    "c010":"드론","c020":"액션캠","c030":"액션캠 렌즈·필터","c040":"핸드짐벌","c060":"드론·액션캠 액세서리","c000":"기타 드론·액션캠",
    "h010":"무선 영상 송수신","h000":"기타 송수신",
}

def _kw(*ws):
    return [w.lower() for w in ws]

# ── 규칙: (대, 중, 키워드들). 위에서부터 첫 매칭. specific → general. ──
RULES = [
 # ── c0 드론·액션캠 (아주 특정 토큰 먼저) ──
 ("c0","c010", _kw("드론","drone","mavic","dji air","air 3","air 2","avata","dji neo","dji flip","fpv","inspire")),
 ("c0","c020", _kw("gopro","고프로","hero 13","hero 12","hero11","hero 11","osmo action","오즈모 액션","액션5","액션 5","action 6","action 5","action 3","action 2","insta360","인스타360","osmo pocket","오즈모 포켓","osmo 360","dji pocket","dji osmo action","action cam","액션캠")),
 ("c0","c030", _kw("action lens","고프로 렌즈")),
 # ── 06a0 스마트폰 리그 (khronos/iphone) ──
 ("06","06a0", _kw("khronos","크로노스","for iphone","아이폰","smartphone","스마트폰","osmo mobile","오즈모 모바일","for samsung","for oppo","phone case","폰 케이스")),
 # ── h0 영상 송수신기 ──
 ("h0","h010", _kw("송수신","transmission","트랜스미","wireless video","무선 영상","teradek","hollyland","홀리랜드","mars ","pyro","air unit","video tx","hdmi 송출","영상송출","sdi 송출","bolt ")),
 # ── 04 시네마렌즈 (PL/시네/아나모픽/T-stop/디조필름 프라임·줌 시리즈) ──
 ("04","0410", _kw("아나모픽","anamorph","pavo","파보")),
 ("04","0420", _kw("시네 줌","cine zoom","줌렌즈 t","zoom lens t","pictor zoom","픽토줌","catta zoom","카타줌","cine 줌","catta")),
 ("04","0410", _kw("시네 프라임","cine prime","프라임 렌즈","vespid","베스피드","pictor prime","마린 프라임")),
 ("04","0430", _kw("시네 매크로","cine macro")),
 ("04","0440", _kw("익스팬더","expander 1.5","lens expander")),
 ("04","0460", _kw("시네렌즈","cine lens","pl마운트","pl 마운트"," pl&ef"," pl & ef","ef마운트 시네","dzo-","dzofilm","디조필름","pictor","픽토")),
 # ── 02 필터 (렌즈 앞 광학필터. 매트박스 본체는 06으로) ──
 ("02","0240", _kw("filter tray","필터 트레이","필터트레이","4x5.65","4×5.65","6x6","4x4","6×6","4x5.6","4×5.6","사각필터","square filter")),
 ("02","0250", _kw("마그네틱 필터","magnetic filter","마그네틱필터","마그네틱 nd","마그네틱 cpl","스위프트")),
 ("02","0260", _kw("clip-in","클립인","clip in filter")),
 ("02","0230", _kw("black mist","블랙 미스트","블랙미스트","mist filter","미스트 필터","diffusion","pearlaura","glimmerglass","streak","스트릭","effect filter","효과필터","illusion")),
 ("02","0220", _kw(" nd필터","nd 필터","nd filter","가변nd","가변 nd","vnd","variable nd","nd1000","nd0.9","nd 0.9","nd 3","nd8","nd16","nd64")),
 ("02","0210", _kw("cpl","c-pl","편광","polariz","uv필터","uv 필터"," uv ","프로텍터 필터","protect filter")),
 ("02","0200", _kw("필터","filter")),  # 광학필터 폴백 (필터 본체 매트박스는 아래 06 규칙이 먼저 못잡음 주의)
 # ── s0 사운드·마이크 (조명보다 먼저 매칭) / 07 조명 ──
 ("s0","s010", _kw("마이크","microphone"," mic ","lavalier","라발리에","shotgun","샷건","무선 마이크","wireless mic","젠하이저","sennheiser","rode ","로데 ","shure","슈어","솔리드컴","라크","wireless go","무선마이크")),
 ("s0","s020", _kw("윈드스크린","windscreen","deadcat","데드캣","붐 폴","boom pole","붐폴","xlr 케이블","마이크 홀더","mic holder","mic 클램프")),
 ("s0","s030", _kw("헤드폰","headphone","헤드셋","headset","이어폰","earphone","모니터링 이어")),
 ("07","0720", _kw("바돌","barn door","반도어","소프트박스","softbox","그리드","softgrid","라이트 스탠드","light stand","조명 스탠드","돔 디퓨저","dome diffuser","리플렉터","reflector","light dome","랜턴 소프트박스")),
 ("07","0710", _kw("조명","led 라이트","led light","cob","fresnel","프레넬","지속광","순간광","strobe","스트로브","플래시","flash","패널 라이트","panel light","tube light","튜브 라이트","라이트 완드","light wand","aputure","어퓨쳐","아푸투레","nanlite","난라이트","amaran","아마란","nanlux","astera","아스테라","라이트")),
 # ── 06 영상장비 ──
 ("06","0640", _kw("팔로우포커스","follow focus","nucleus","뉴클레어스","포커스 모터","focus motor","wireless lens control","렌즈 컨트롤","lens control","focus gear ring","포커스 기어링","focus handwheel","핸드휠")),
 ("06","0630", _kw("매트박스","matte box","mattebox","mirage","미라지 매트")),
 ("06","0670", _kw("짐벌","gimbal","stabiliz","스태빌라이저","ronin","로닌","crane","크레인","float ","armor man","armorman","암 오브 갓","gimbal support","짐벌 서포트","hydra ","히드라","dji rs","dji ronin")),
 ("06","0680", _kw("배터리","battery","충전기","charger","v마운트","v-mount","v 마운트","np-f","np-fz","d-tap","dtap","gold-mount","골드마운트","dummy batter","더미 배터리","power distribution","파워 디스트리","battery plate","배터리 플레이트","power supply","전원 어댑터","battery adapter","충전 스테이션","charging station","power module")),
 ("06","0620", _kw("케이지","cage","베이스플레이트","baseplate","base plate","top plate","탑플레이트","half cage","full cage","camera cage","리그 키트","rig kit","base kit","라이트 키트 black")),
 ("06","0650", _kw("탑 핸들","top handle","탑핸들","side handle","사이드 핸들","사이드핸들","wooden grip","우드 그립","우든 핸들","wooden handle","hand grip","핸드 그립","rosette","로제트","핸들 ","handle "," handle","pistol grip")),
 ("06","0660", _kw("숄더","shoulder","숄더리그","shoulder rig","dovetail shoulder","숄더 마운트")),
 ("06","06b0", _kw("슬라이더","slider","달리","dolly","모션 컨트롤 슬라이더")),
 ("06","06c0", _kw("모니터","monitor","뷰파인더","viewfinder","evf","텔레프롬프터","teleprompter","모니터 케이지","monitor cage")),
 ("06","0690", _kw("cold shoe","콜드슈","nato","나토","매직암","magic arm"," arm ","클램프","clamp","마운트","mount","브라켓","bracket","cheese","치즈","ssd holder","cooling system","쿨링","냉각","speed rail","rod holder","로드 홀더","rod ","베이스 액세서리","안티 트위스트","adapter plate","dovetail","도브테일","suction cup","석션","나사","screw","스피곳","spigot","allen key","육각","spud","스터드","stud","안전 와이어","safety")),
 # ── 05 카메라가방 ──
 ("05","0530", _kw("하드케이스","hard case","펠리칸","pelican","케이스","case","롤러 케이스")),
 ("05","0510", _kw("백팩","backpack")),
 ("05","0520", _kw("숄더백","shoulder bag","메신저백","messenger")),
 ("05","0550", _kw("파우치","pouch","테크 파우치","tech pouch")),
 ("05","0560", _kw("렌즈 케이스","lens case","필터 케이스","filter case","필터 파우치")),
 ("05","0500", _kw("가방","bag ","camera bag")),
 # ── 03 카메라렌즈 (시네 마커 없는 사진렌즈) ──
 ("03","0330", _kw("렌즈 어댑터","lens adapter","마운트 어댑터","mount adapter","ef-e","ef to e","렌즈어댑터","autofocus adapter")),
 ("03","0340", _kw("렌즈 서포트","lens support","렌즈 후드","lens hood","포커스 기어","gear ring")),
 ("03","0350", _kw(" rf ","rf마운트","rf 마운트","rf렌즈")),
 ("03","0310", _kw("장망원렌즈","망원렌즈","광각렌즈","표준렌즈","단렌즈","줌렌즈","미러리스 렌즈","sel","fe 렌즈"," lens"," 렌즈")),
 # ── 08 테더툴스 ──
 ("08","0810", _kw("테더","tether","tetherpro","테더프로")),
 # ── 06 파워/더미 케이블 (09 잡동사니로 새지 않게 먼저) ──
 ("06","0680", _kw("더미 케이블","더미케이블","dummy cable","p-tap","d-tap to","파워 케이블","power cable","dc male","dc female","battery adapter cable","전원 케이블")),
 # ── 09 액세서리 ──
 ("09","0960", _kw("리더기","card reader","리더","express ssd"," ssd ","포터블 ssd","메모리 카드","메모리카드","memory card","cf-express","cfexpress","cf익스프레스","sd카드","sd 카드")),
 ("09","0950", _kw("테크랩","techrap","tech wrap","렌즈 랩","보호랩","보호 랩","스킨","skin ")),
 ("09","0920", _kw("스트랩","strap","넥스트랩","neck strap","핸드 스트랩")),
 ("09","0930", _kw("장갑","glove")),
 ("09","0940", _kw("청소","cleaning","클리닝","블로워","blower","클리너")),
 ("09","0910", _kw("카메라 뱃지","badge","뱃지")),
 # ── 01 삼각대 (비디오삼각대는 위 06 미매칭분만 도달) ──
 ("06","0610", _kw("비디오 삼각대","video tripod","cine tripod","시네 삼각대","플루이드 헤드 삼각대","비디오삼각대")),
 ("01","0120", _kw("볼헤드","ballhead","ball head","플루이드 헤드","fluid head","기어 헤드","gear head","gimbal head","짐벌헤드","삼각대 헤드","tripod head","팬 헤드")),
 ("01","0150", _kw("클램프","clamp","슈퍼클램프","super clamp","봉고타이","봉고 타이","무대클램프")),
 ("01","0140", _kw("퀵릴리즈 플레이트","quick release plate","qr plate","arca plate","아르카 플레이트","플레이트")),
 ("01","0110", _kw("삼각대","tripod","모노포드","monopod","스탠드 베이스","레그","legs","c스탠드","c-stand","라이트 스탠드")),
 ("01","0130", _kw("삼각대 액세서리","스파이크","spike","삼각대 가방")),
 # ── 00 카메라·바디 (모델토큰 아닌 '바디임' 신호만 — clmedia 실제 바디) ──
 ("00","0000", _kw("풀프레임 미러리스","풀프레임미러리스","미러리스 카메라","미러리스카메라","풀프레임카메라","풀프레임 카메라",
                    "캠코더","camcorder","시네마 라인","시네마라인","cinema line","방송용 카메라","ursa cine","ursa mini","ursa broadcast",
                    "ilce-","ilme-","pxw-","hc-x","시네마 카메라","시네 카메라")),
 # ── 카메라모델 번들/키트 = 리그·케이지 키트 (06). 위 규칙 미매칭 잔여 kit 흡수 ──
 ("06","0620", _kw(" kit","키트")),
]

# 원본 category → (대,중) 힌트 (제품명 규칙 미매칭 시 폴백)
CAT_HINT = {
    "lighting": ("07","0710"),
    "audio": ("s0","s010"),
    "monitor": ("06","06c0"),
    "grip": ("06","0690"),
    "camerasupport": ("06","0620"),
    "lenses/filters": ("03","0300"),
    "camera": ("00","0000"),
    "power cables": ("06","0680"),
    "camera cart": ("06","0690"),
}

# 대분류별 "기타" 중 코드
DAE_MISC = {"00":"0000","01":"0160","02":"0200","03":"0300","04":"0400","05":"0500",
            "06":"0600","07":"0700","s0":"s000","08":"0800","09":"0900","c0":"c000","h0":"h000"}

# 시네렌즈 T-stop 패턴(T2.9, T 1.5 등) + 렌즈/mm 문맥
_TSTOP = re.compile(r"\bt\s?\d\.\d")

def _out(dae, jung):
    return dae, DAE[dae], jung, JUNG.get(jung, JUNG[DAE_MISC[dae]])

def classify(name, category=""):
    t = (name or "").lower()
    for dae, jung, kws in RULES:
        for k in kws:
            if k in t:
                return _out(dae, jung)
    # T-stop 있는 렌즈류 → 시네렌즈 (프라임/줌 구분은 zoom 토큰)
    if _TSTOP.search(t) and ("렌즈" in t or "lens" in t or "mm" in t):
        return _out("04", "0420" if ("zoom" in t or "줌" in t) else "0410")
    # 원본 category 힌트 (제품명으로 못 잡은 clmedia 대분류)
    c = (category or "").strip().lower()
    if c in CAT_HINT:
        dae, jung = CAT_HINT[c]
        return _out(dae, jung)
    # 최종 폴백
    return _out("09", "0900")
