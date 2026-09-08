"""Cross-brand product browsing based on KPP's public category tree.

Preserve source memberships and prices. Add our own product-type paths with
evidence, and retain ambiguous items in a general category for later review.
"""
import re
import unicodedata
from collections import Counter


# New leaves supplement the KPP groups; their names describe product types.
EXTRA = [
 ('robot-vacuum',None,'로봇 청소기'),('robot-vacuum-body','robot-vacuum','로봇 청소기 본체'),('robot-vacuum-parts','robot-vacuum','로봇 청소기 소모품·액세서리'),
 ('mini-light','kpp:0710','미니 라이트'),('mat-light','kpp:0710','매트 라이트'),('car-mount','kpp:06','카마운팅'),('light-power','kpp:0720','조명 케이블·전원'),('light-bag','kpp:0720','조명 가방·케이스'),
 ('mount-adapter','kpp:0690','마운팅 어댑터'),('audio-adapter','kpp:0740','오디오 변환 어댑터'),('camera-markers','kpp:09','카메라 마커·현장 소모품'),('dry-cabinet','kpp:09','제습함·보관용품'),('drone-parts','kpp:c010','드론 부품'),
 ('tv-display',None,'TV·디스플레이'),('tv','tv-display','TV'),('projector','tv-display','프로젝터·스크린'),('light-meter','kpp:0720','노출계·조명 동조기'),('jib','kpp:06','지브·크레인'),('turntable','kpp:06','턴테이블'),('camera',None,'카메라'),('mirrorless','camera','미러리스 카메라'),('dslr','camera','DSLR 카메라'),('cinema-camera','camera','시네마 카메라'),('camcorder','camera','캠코더'),('compact-camera','camera','컴팩트·즉석 카메라'),
 ('medium-camera','camera','중형 카메라'),('medium-lens','kpp:03','중형 렌즈'),('phone-lens','kpp:03','스마트폰 렌즈'),
 ('dolly','kpp:06b0','카메라 달리'),('apple-box','kpp:09','애플박스'),
 ('carbon','kpp:0110','카본 삼각대'),('aluminum','kpp:0110','알루미늄 삼각대'),('mini-tripod','kpp:0110','미니·테이블 삼각대'),('travel-tripod','kpp:0110','여행용 삼각대'),('monopod','kpp:01','모노포드'),
 ('ball-head','kpp:0120','볼헤드'),('video-head','kpp:0120','비디오 헤드'),('gear-head','kpp:0120','기어 헤드'),('gimbal-head','kpp:0120','짐벌 헤드'),('pan-head','kpp:0120','3WAY·파노라마 헤드'),
 ('uv','kpp:0210','UV·보호 필터'),('cpl','kpp:0210','CPL·편광 필터'),('vnd','kpp:0220','가변 ND 필터'),('fixed-nd','kpp:0220','고정 ND 필터'),('nd-pl','kpp:0220','ND·PL 복합 필터'),('mist','kpp:0230','미스트·소프트 필터'),('filter-parts','kpp:02','홀더·어댑터링·캡'),
 ('wide-lens','kpp:03','광각·초광각 렌즈'),('standard-lens','kpp:03','표준 렌즈'),('tele-lens','kpp:03','망원·초망원 렌즈'),('macro-lens','kpp:03','매크로 렌즈'),
 ('sling-bag','kpp:0520','슬링·크로스백'),('rolling-case','kpp:0530','롤링·하드 케이스'),('equipment-bag','kpp:05','조명·장비 가방'),
 ('rig-arms','kpp:0690','매직암·관절암'),('rig-mounts','kpp:0690','브라켓·마운트'),('rig-rods','kpp:0690','로드·로드 클램프'),('rig-screws','kpp:0690','나사·스피곳·어댑터'),('rig-carts','kpp:06','촬영 카트·달리'),('teleprompter','kpp:06','텔레프롬프터'),
 ('flash','kpp:07','스트로보·플래시'),('continuous','kpp:0710','지속광·포인트 조명'),('panel-light','kpp:0710','패널 조명'),('tube-light','kpp:0710','튜브·RGB 조명'),
 ('softbox','kpp:0720','소프트박스·랜턴'),('reflector','kpp:0720','반사판·스크림·플래그'),('light-shaping','kpp:0720','그리드·스누트·바운스'),('light-lens','kpp:0720','프레넬·스포트라이트 렌즈'),('light-stand','kpp:0720','조명 스탠드·C스탠드'),('light-grip','kpp:0720','클램프·그립·붐'),('background','kpp:0720','배경지·배경 시스템'),('lighting-gels','kpp:0720','조명 컬러·확산 필터'),
 ('audio',None,'마이크·오디오'),('wireless-mic','kpp:0730','무선 마이크'),('wired-mic','kpp:0730','유선·샷건 마이크'),('studio-mic','kpp:0730','스튜디오·USB 마이크'),('intercom','audio','인터컴·무선 인터폰'),('audio-recorder','audio','레코더·오디오 인터페이스'),('audio-mixer','audio','오디오 믹서·앰프'),('speakers','audio','모니터 스피커'),('instruments','audio','키보드·신시사이저'),
 ('power',None,'배터리·전원'),('v-mount','kpp:0680','V마운트·방송용 배터리'),('camera-battery','kpp:0680','카메라·조명 배터리'),('chargers','power','충전기'),('power-station','power','파워뱅크·발전기'),('power-parts','power','배터리 플레이트·전원 어댑터'),
 ('video-wireless','kpp:h0','무선 영상 송수신기'),('monitor','kpp:h0','촬영·편집 모니터'),('video-recorder','kpp:h0','외장 레코더'),('switcher','kpp:h0','스위처·라이브 방송'),('converter','kpp:h0','컨버터·캡처·분배기'),('video-control','kpp:h0','영상 제어·컨트롤 패널'),
 ('gimbal-parts','kpp:c040','짐벌 액세서리'),('action-parts','kpp:c020','액션캠 액세서리'),('usb-cable','kpp:08','USB·테더 케이블'),('hdmi-cable','kpp:08','HDMI 케이블'),('sdi-cable','kpp:08','SDI·BNC 케이블'),('audio-cable','kpp:08','오디오 케이블'),('cable-parts','kpp:08','케이블·연결 액세서리'),
 ('air-blower','kpp:0940','에어블로워'),('cleaning','kpp:0940','클리닝 키트·천'),('tools','kpp:09','공구·멀티툴'),('remote','kpp:09','리모컨·릴리즈'),('storage','kpp:09','메모리·저장장치'),('sd-card','storage','SD·MicroSD'),('cf-card','storage','CF·CFexpress'),('ssd','storage','SSD·스토리지'),('other','kpp:09','기타 촬영용품'),
 ('display-mount',None,'모니터암·TV 거치대'),('software',None,'소프트웨어·편집 장비'),('editing-software','software','편집·컬러 소프트웨어'),('editing-control','software','편집 컨트롤러·태블릿'),('print-color',None,'프린트·컬러 관리'),('print','print-color','프린터·잉크·용지'),('color','print-color','컬러차트·캘리브레이션'),('studio',None,'스튜디오·촬영 서비스'),
]

NAVER = {
 '50002074':'kpp:0110','50002075':'monopod','50002076':'kpp:0120','50002077':'kpp:0140','50002079':'kpp:0130','50002078':'equipment-bag',
 '50004609':'kpp:02','50004610':'kpp:0330','50004605':'wide-lens','50004604':'standard-lens','50004606':'tele-lens','50004614':'kpp:0560',
 '50000266':'mirrorless','50000265':'dslr','50004619':'dslr','50000267':'compact-camera','50000268':'camcorder',
 '50004633':'kpp:0530','50004634':'kpp:0520','50004635':'kpp:0510','50004637':'equipment-bag','50002073':'kpp:0920',
 '50002080':'kpp:07','50002082':'background','50002086':'camera-battery','50002089':'camera-battery','50002084':'chargers','50002088':'chargers','50017740':'power-station','50003442':'power-station','50003113':'power-station',
 '50002102':'kpp:0730','50002326':'wired-mic','50002327':'wireless-mic','50006972':'studio-mic','50024359':'studio-mic','50002328':'kpp:0740',
 '50024419':'kpp:0750','50024439':'kpp:0750','50024459':'kpp:0750','50024479':'kpp:0750','50002342':'kpp:0750','50002974':'audio-recorder','50001966':'audio-mixer','50001964':'audio-mixer','50002320':'speakers','50004320':'instruments',
 '50003120':'usb-cable','50000252':'usb-cable','50003118':'hdmi-cable','50004630':'kpp:0960','50004625':'sd-card','50004624':'sd-card','50004626':'cf-card',
 '50000153':'monitor','50002977':'converter','50002979':'editing-software','50001516':'editing-software','50002935':'editing-control','50002936':'editing-control','50002948':'print',
 '50002098':'remote','50006129':'kpp:c010','50006369':'kpp:c040','50007304':'studio','50002112':'kpp:0940','50006203':'display-mount','50001315':'rig-carts','50002703':'rig-carts','50006370':'kpp:06a0','50000255':'kpp:06a0',
}

# Accessory nouns precede camera/lens model names, so "FX3 cage" is not a camera.
RULES = [
 ('studio',r'스튜디오|촬영\s*서비스|호리존'),
 ('color',r'컬러\s*차트|컬러체커|colorchecker|캘리브레|calibrat|스파이더\s*[xX]|spyder'),
 ('editing-control',r'speed\s*editor|replay\s*editor|키보드|keyboard|컨트롤\s*패널|micro\s*panel|mini\s*panel|advanced\s*panel|와콤|타블렛'),
 ('editing-software',r'다빈치\s*리졸브\s*스튜디오|davinci resolve studio|capture\s*one|라이선스|소프트웨어'),
 ('print',r'프린터|프린팅|잉크|ink\b|출력\s*용지|사진\s*용지|포토\s*용지'),
 ('air-blower',r'에어\s*블로|블로워|블로우|air\s*blower|rocket\s*air'),('cleaning',r'클리닝|cleaning|청소\s*키트|렌즈\s*펜|lens\s*pen'),
 ('tools',r'드라이버|screwdriver|멀티\s*툴|multi.?tool|렌치|wrench|tool\s*kit'),
 ('power-parts',r'배터리\s*(?:플레이트|홀더|어댑터|마운트(?!\s*배터리))|battery\s*(?:plate|holder|adapter|mount)|(?:전원|power|AC).*(?:어댑터|adapto?r)|파워\s*뱅크\s*홀더'),
 ('chargers',r'충전기|charger'),('power-station',r'파워\s*뱅크|power\s*bank|power\s*station|발전기|태양광|solar\s*panel'),
 ('hdmi-cable',r'HDMI.*(?:케이블|cable)|(?:케이블|cable).*HDMI'),('sdi-cable',r'(?:SDI|BNC).*(?:케이블|cable)'),('audio-cable',r'(?:XLR|TRS|오디오).*(?:케이블|cable)'),('usb-cable',r'(?:USB|테더|tether).*(?:케이블|cable)'),('cable-parts',r'케이블|cable|케이블\s*타이'),
 ('kpp:0560',r'(?:렌즈|필터|lens|filter).*(?:케이스|파우치|case|pouch)'),
 ('kpp:0550',r'테크\s*랩|테크\s*파우치|tech\s*(?:wrap|pouch)'),('kpp:0510',r'백팩|배낭|backpack'),('sling-bag',r'슬링|sling|크로스\s*백'),('kpp:0520',r'숄더\s*백|shoulder\s*bag|메신저'),('rolling-case',r'하드\s*케이스|hard\s*case|롤링|rolling|펠리칸'),('equipment-bag',r'가방|캐리\s*백|carry.*bag|\bbag\b'),('kpp:0530',r'케이스|\bcase\b|보호\s*커버'),
 ('filter-parts',r'필터.*(?:링|홀더|캡)|filter.*(?:ring|holder|cap)|스텝\s*(?:업|다운)|step.?up|step.?down'),
 ('kpp:0260',r'클립\s*인\s*필터|clip.?in.*filter'),('vnd',r'가변.*필터|\bVND\b|variable\s*(?:ND|density)'),('nd-pl',r'ND\s*[-/]?\s*PL'),('kpp:0220',r'\bND\d|ND\s*필터|엔디\s*필터'),('cpl',r'\bCPL\b|편광\s*필터|polariz'),('uv',r'\bUV\b.*필터|보호\s*필터|프로텍터.*필터'),('mist',r'미스트|\bmist\b|블랙\s*디퓨[전젼]'),
 ('kpp:0330',r'렌즈.*(?:어댑터|어뎁터|컨버터)|lens.*adapt|스피드\s*부스터'),('kpp:0340',r'렌즈\s*후드|lens\s*hood|렌즈\s*캡|lens\s*cap|포커스\s*기어'),
 ('kpp:0630',r'매트\s*박스|매트\s*박|matte\s*box'),('kpp:0640',r'nucleus|뉴클리어스|팔로우\s*포커스|follow\s*focus|포커스\s*모터|focus\s*motor'),('kpp:0620',r'케이지|\bcage\b'),('kpp:0660',r'숄더\s*리그|숄더\s*패드|shoulder\s*(?:rig|pad)'),('kpp:0650',r'핸들|\bhandle\b|사이드\s*그립|엘쉐이프\s*그립'),
 ('kpp:0140',r'플레이트|퀵\s*슈|\bplate\b|quick\s*shoe'),('rig-rods',r'\brod\b|\brods\b|\d\s*mm\s*로드'),('rig-arms',r'매직\s*암|magic\s*arm|관절\s*암|articulating\s*arm'),('rig-screws',r'스피곳|spigot|스피것|스크류|\bscrew\b|\bstud\b|나사|스피갓'),
 ('kpp:06b0',r'슬라이더|slider'),('dolly',r'\bdolly\b|달리|돌리'),('rig-carts',r'카트|\bcart\b'),('apple-box',r'애플\s*박스|apple\s*box'),('teleprompter',r'프롬프터|prompter'),
 ('kpp:0740',r'쇼크\s*마운트|shock\s*mount|윈드\s*스크린|wind\s*screen|윈드\s*쉴드|windshield|데드\s*캣|dead\s*cat|팝\s*필터|pop\s*filter|마이크\s*(?:스탠드|홀더|마운트|클립)|mic.*(?:stand|holder|clip)'),
 ('light-meter',r'노출계|동조기|light\s*meter|sekonic'),('turntable',r'턴테이블|turntable'),('tv',r'\bTV\b|티비|텔레비전'),('projector',r'프로젝터|projector|프로젝션\s*스크린'),('intercom',r'인터컴|인터폰|intercom|solidcom|솔리드컴'),('wireless-mic',r'무선\s*마이크|wireless\s*(?:mic|go|pro)|lark|라크|DJI\s*(?:mic|마이크)'),('studio-mic',r'콘덴서.*마이크|condenser.*mic|USB.*마이크'),('kpp:0730',r'마이크(?!로)|microphone|\bmic\b'),('kpp:0750',r'헤드폰|헤드셋|이어폰|headphone|headset|earphone'),('speakers',r'스피커|speaker'),('audio-mixer',r'오디오\s*믹서|audio\s*mixer|앰프|amplifier'),('audio-recorder',r'오디오\s*인터페이스|audio\s*interface|필드\s*레코더|field\s*recorder|handy\s*recorder'),
 ('softbox',r'소프[트르]\s*박스|light\s*dome|엄브렐라|umbrella|soft\s*box|softbox|랜턴|lantern|octa'),('light-shaping',r'스누트|snoot|반도어|바운스|barn.?door|허니콤|honeycomb|그리드|grid'),('reflector',r'반사판|reflector|스크림|\bscrim\b|플래그|\bflag\b|플랙|플로피|floppy|버터플라이|butterfly|확산판|디퓨저|고보|\bgobo\b'),('light-lens',r'프레넬|fresnel|프로젝션|projection|spotlight'),('lighting-gels',r'젤\s*필터|gel\s*filter|컬러\s*필터.*롤|확산\s*필터'),('background',r'배경|익스판|background|backdrop|chroma|크로마키'),
 ('light-stand',r'(?:조명|라이트|light|C[- ]?|롤러|roller|콤보|combo|센츄리|century|wind.up)\s*(?:스탠드|stand)|\b[CS]T-\d.*stand'),('light-grip',r'붐\s*암|boom|그립\s*헤드|grip\s*head|샌드\s*백|sand\s*bag|모래주머니'),
 ('kpp:0150',r'클램프|\bclamp\b'),('kpp:0130',r'삼각대.*(?:고무|스파이크|발|액세서리)|tripod.*(?:feet|spike|accessor)'),('monopod',r'모노포드|monopod'),('video-head',r'(?:비디오|video).*헤드|fluid\s*head'),('gear-head',r'기어\s*헤드|gear.*head'),('ball-head',r'볼\s*헤드|ball\s*head'),('kpp:0120',r'삼각대\s*헤드|tripod\s*head'),('kpp:0610',r'(?:비디오|video).*삼각대|video\s*tripod'),('kpp:0110',r'삼각대|tripod'),
 ('kpp:0680',r'배터리|battery|batteries'),
 ('phone-lens',r'(?:아나모픽|anamorphic|macro).*?(?:렌즈|lens).*?(?:mobile|phone|T.mount)|(?:macro|anamorphic)\s*lens\s*\(T.mount\)'),
 ('kpp:04',r'\d\s*mm\s*T\s*\d|시네마\s*렌즈|cine\s*lens'),
 ('kpp:03',r'\d\s*mm\s*F\s*\d'),
 ('rig-mounts',r'브라켓|브래킷|bracket|마운트|\bmount\b|거치대|홀더|holder|서포트|support|클립|\bclip\b'),
 ('kpp:0680',r'배터리|battery|batteries'),('kpp:0920',r'스트랩|strap'),('cf-card',r'CFexpress|CFE[- ]|CF\s*카드|compact\s*flash'),('sd-card',r'micro\s*sd|SD\s*카드|SDXC|SDHC'),('kpp:0960',r'리더기|card\s*reader'),('ssd',r'\bSSD\b|cloud\s*store|media\s*(?:module|dock)'),
 ('video-wireless',r'영상.*(?:송신|수신)|(?:송신|수신).*영상|wireless\s*video|pyro\s*[HS]|mars\s*\d|\btransmission\b|트랜스미션|teradek.*bolt|cosmo\s*C1'),('video-recorder',r'hyperdeck|video\s*assist|외장\s*레코더|ninja|shogun'),('converter',r'컨버터|converter|캡처|capture\s*card|decklink|intensity|분배기|distributor'),('switcher',r'스위처|switcher|\bATEM\b|web\s*presenter'),('monitor',r'모니터|monitor|viewfinder|뷰파인더|\bEVF\b'),
 ('kpp:c050',r'care\s*refresh|케어\s*리프레시'),('gimbal-parts',r'짐벌.*(?:액세서리|부품)|gimbal.*accessor'),('kpp:c040',r'짐벌|gimbal|ronin|로닌|osmo\s*mobile|오즈모\s*모바일'),('kpp:c020',r'액션\s*캠|osmo\s*(?:action|pocket|360)|오즈모\s*(?:액션|포켓|360)|gopro|고프로|insta360'),('kpp:c010',r'드론|drone|mavic|매빅|\bavata\b|\blito\b|리토|DJI\s*(?:mini|air|flip|neo|inspire|매트리스)'),
 ('flash',r'스트로보|strobe|플래시|\bflash\b|스피드라이트'),('tube-light',r'튜브|tube|pavotube|파보튜브'),('panel-light',r'패널.*조명|panel.*light|룩스패드|luxpad'),('kpp:0710',r'LED|\bCOB\b|조명|라이트|\blight\b|forza|포르자|evoke|이보크'),
 ('cinema-camera',r'시네마\s*카메라|cinema\s*camera|\bPYXIS\b|\bURSA\b|\bFX[369]\b'),('mirrorless',r'미러리스|mirrorless'),('dslr',r'DSLR'),('camera',r'카메라|\bcamera\b'),
 ('kpp:03',r'렌즈|\blens\b'),('remote',r'리모컨|릴리즈|remote|release\s*control'),
]
COMPILED=[(target,re.compile(pattern,re.I)) for target,pattern in RULES]
LIGHT_BRANDS={'godox','nanlite','nanlux','aputure','fomex','broncolor','aurora','parabolix','harlowe','savage'}
GRIP_BRANDS={'kupo','matthews','avenger','valens','kumkwang'}


def camera_accessory_type(name,brand):
    """Reject accessory nouns mistaken for the camera they fit.

    Applied to camera candidates only, not to verified rental body packages.
    Specific electrical/optical adapters precede mechanical mounting adapters.
    """
    if re.search(r'필름카메라.*필터.*키트|(?:카메라|바디).*(?:사은품|증정)',name,re.I):
        return None
    rules=[
      ('power-parts',r'(?:전원|배터리|power|battery|\bAC\b).*(?:어[댑뎁]터|adapto?r)'),
      ('audio-adapter',r'(?:3[.]5\s*mm|TRRS|TRS|XLR).*(?:어[댑뎁]터|adapto?r)'),
      ('filter-parts',r'필터.*(?:어[댑뎁]터|어[댑뎁]타|adapter)|filter.*adapt'),
      ('kpp:0330',r'(?:렌즈|lens).*(?:어[댑뎁]터|어[댑뎁]타|adapto?r)'),
      ('mount-adapter',r'어[댑뎁]터|어[댑뎁]타|\badapto?r\b'),
      ('kpp:0620',r'케이지|\bcage\b'),('kpp:0140',r'플레이트|\bplate\b|퀵\s*릴리즈|quick\s*release'),
      ('kpp:0650',r'핸드그립|우든그립|\bgrip\b'),
      ('cf-card',r'CF\s*익스프레스|CFexpress'),('sd-card',r'\bSDXXD\b|\bSDXC\b|\bSDHC\b'),('storage',r'메모리|\bmemory\b'),
      ('cleaning',r'청소|클리너|극세사|면봉|cleaner|swab'),
      ('kpp:0340',r'링캡|보호캡|렌즈\s*캡'),
      ('kpp:02',r'필터|\bfilter\b'),
      ('dry-cabinet',r'제습함|dry\s*cabinet'),
      ('equipment-bag',r'파우치|pouch'),('kpp:0530',r'레인커버|rain\s*cover'),
      ('camera-markers',r'티마커|아이마커|camera\s*(?:T\s*)?marker'),
      ('rig-mounts',r'카메라\s*(?:스탠드|라이저)|camera\s*(?:riser|platform)|콜드슈|연장암'),
      ('rig-mounts',r'피벗\s*조인트'),('pan-head',r'팬헤드|팬틸트\s*헤드|PAN.*HEAD'),
      ('jib',r'지미집|\bjib\b|크레인|\bcrane\b'),
      ('video-control',r'PTZ.*(?:컨트롤러|controller)|조이스틱'),
      ('remote',r'리모컨|릴리즈|remote'),
      ('video-recorder',r'\bURSA\s+Mini\s+Recorder\b'),
      ('drone-parts',r'Air\s*Unit.*Camera\s*Module'),
      ('action-parts',r'액션\s*카메라.*(?:액세서리|셀카봉)'),
      ('other',r'핫슈.*(?:커버|수평계)|플립미러|shim\s*kit|\bENG\s*Kit\b|ProDock|Live\s*Encoder|프런트박스|front\s*box'),
    ]
    for target,pattern in rules:
        if re.search(pattern,name,re.I):return target
    if brand in {'smallrig','tilta'} and re.search(r'(?:FX[369]|FX30).*?(?:키트|kit)',name,re.I):return 'kpp:0620'
    if brand=='edelkrone' and re.search(r'헤드|head|FlexTILT',name,re.I):return 'kpp:0120'
    if brand=='harlowe' and re.search(r'솔\s*5|SOL\s*5',name,re.I):return 'kpp:0710'
    return None


def aputure_type(name, category_ids):
    # The user's Aputure purchase source is AVX; optical lighting accessories
    # must never enter the camera-lens tree because their title says "lens".
    for target, pattern in [
        ('light-power', r'케이블|cable|충전기|charger|전원.*어댑터'),
        ('light-bag', r'케이스|case|가방|bag'),
        ('light-grip', r'어댑터|adapter|브라켓|브래킷|bracket|클램프|clamp|요크|yoke|connector|커넥터'),
        ('light-shaping', r'그리드|grid|barn.?door|반도어|고보|gobo|아이리스|iris'),
        ('softbox', r'soft.?box|소프트박스|dome|돔|lantern|랜턴|light.?box|라이트박스'),
        ('light-lens', r'프레[즈]?넬|프리즈넬|fresnel|spotlight|스포트라이트|parallel.?beam|리플렉터|reflector'),
        ('light-stand', r'스탠드|stand'),
        ('mat-light', r'infinimat|인피니매트'),
        ('tube-light', r'infinibar|인피니바|튜브|tube|MT.?Pro'),
        ('panel-light', r'nova|노바|패널|panel'),
        ('mini-light', r'\bMC\b|미니'),
        ('continuous', r'storm|스톰|\bLS\b|\bCS\d|\d+[dcx]\b'),
    ]:
        if re.search(pattern, name, re.I): return target
    if any('00200007' in cid for cid in category_ids): return 'kpp:0720'
    return 'kpp:0710'


def build_taxonomy(products,categories,overrides=None):
    nodes={}
    def add(key,name,parent=None,source=None):
        cid='type:'+key
        nodes[cid]={'id':cid,'name':name,'parent_id':'type:'+parent if parent else None,'brand_id':None,'scope':'product','source_id':source}
    for c in list(categories.values()):
        if c['id'].startswith('kpp:p:'):
            add('kpp:'+c['id'].split(':')[-1],c['name'],'kpp:'+c['parent_id'].split(':')[-1] if c['parent_id'] else None,c['id'])
    for key,parent,name in EXTRA:add(key,name,parent)
    for key,name in [('kpp:07','조명'),('kpp:08','케이블·테더링'),('kpp:h0','영상 송수신·모니터'),('kpp:c0','드론·액션캠·짐벌'),('kpp:09','촬영 액세서리')]:nodes['type:'+key]['name']=name
    for key in ('0730','0740','0750'):nodes['type:kpp:'+key]['parent_id']='type:audio'
    nodes['type:kpp:0680']['parent_id']='type:power'
    for c in list(categories.values()):
        if c['id'].startswith('l-mount:b:ldl-mount:'):
            add('mount:'+c['id'].split(':')[-1],c['name'],'mount:'+c['parent_id'].split(':')[-1] if c['parent_id'] else 'display-mount',c['id'])
    roots=['kpp:01','kpp:02','camera','kpp:03','kpp:04','kpp:05','kpp:06','kpp:07','audio','power','kpp:h0','kpp:c0','kpp:08','kpp:09','kpp:00','tv-display','display-mount','software','print-color','studio']
    order={key:i for i,key in enumerate(roots)}
    def path(cid):
        result=[]
        while cid:
            if cid in result or cid not in nodes:raise ValueError('Invalid product category path: '+str(cid))
            result.insert(0,cid);cid=nodes[cid]['parent_id']
        return result
    audit=[]
    for p in products:
        name=unicodedata.normalize('NFKC',p['name']);bid=p['brand_id']
        native=['type:kpp:'+c.split(':')[-1] for c in p['type_ids'] if c.startswith('kpp:p:')]
        mounted=['type:mount:'+c.split(':')[-1] for c in p['category_ids'] if c.startswith('l-mount:b:ldl-mount:')]
        reason='kpp-membership' if native else 'supplier-category' if mounted else ''
        selected=native or mounted
        rental_model=None
        if p['kind']=='rental':
            for key,pattern in [
              ('cinema-camera',r'^(?:소니\s*SONY\s*FX3|SONY\s*소니\s*FX3|RED\s*GEMINI|NIKON\s*니콘\s*ZR)'),
              ('camcorder',r'^(?:소니\s*SONY\s*AX700)'),('compact-camera',r'캐논\s*SX740'),('mirrorless',r'^(?:(?:CANON|캐논)\s*)+R[56]'),
              ('kpp:04',r'CANON\s*CN-E'),('kpp:0320',r'^(?:(?:SONY|소니)\s*)+FE\s*\d'),('medium-lens',r'^PHASEONE\s*LS\s*\d'),('medium-camera',r'^PHASEONE\s*XF\s*IQ'),
              ('kpp:0710',r'(?:HARLOWE|할로우).*?(?:Atom|크리에이터)|MISONICS\s*FLOOD|ARRI\s*Skypanel|APUTURE\s*(?:Amaran\s*)?(?:300C|60X|600D)|NANLUX\s*DYNO'),('kpp:07',r'ARRI\s*True\s*Blue'),('flash',r'Profoto\s*(?:A1X|Pro-B3)'),
              ('kpp:0650',r'DJI\s*TWIST\s*DUAL\s*GRIP'),
              ('kpp:0110',r'맨프로토\s*Compact\s*Action'),('light-stand',r'KUPO\s*CS-[234]0M'),('monitor',r'TVLogic\s*LVM'),('jib',r'EDELKRONE.*집원'),('kpp:06b0',r'EDELKRONE.*슬라이더'),('kpp:0120',r'EDELKRONE.*(?:팬프로|헤드플러스)'),('kpp:c040',r'DJI\s*TILTA\s*RINGGRIP'),
            ]:
                if re.search(pattern,name,re.I):rental_model=key;break
        if not selected and rental_model:selected=['type:'+rental_model];reason='rental-model'
        if not selected:
            if bid=='lee-filters' and re.search(r'롤|낱장|젤|\bSC\d|\b\d{3}\b',name,re.I):selected=['type:lighting-gels'];reason='lighting-filter-source'
            else:
                for target,pattern in COMPILED:
                    if pattern.search(name):selected=['type:'+target];reason='name:'+target;break
            if not selected:
                mapped=next((NAVER[c.split(':')[-1]] for c in p['type_ids'] if c.startswith('naver:p:') and c.split(':')[-1] in NAVER),None)
                if mapped:selected=['type:'+mapped];reason='naver-category'
                elif bid in LIGHT_BRANDS:selected=['type:kpp:07'];reason='brand-family'
                elif bid in GRIP_BRANDS:selected=['type:light-grip'];reason='brand-family'
                else:selected=['type:other'];reason='general-review'
        if p['kind']=='purchase' and any('type:camera' in path(cid) for cid in selected):
            accessory=camera_accessory_type(name,bid)
            if accessory:selected=['type:'+accessory];reason='camera-accessory:'+accessory
        if p['kind']=='purchase' and bid=='aputure':
            selected=['type:'+aputure_type(name,p.get('category_ids',[]))];reason='aputure-lighting-purpose'
        if p['kind']=='purchase' and bid=='dji' and p['id'].startswith('dji-official-'):
            if re.search(r'Care\s*(?:Refresh|Pro)|Extended Protection|연장.*보호',name,re.I):
                selected=['type:kpp:c050'];reason='dji-official-service'
            elif 'dji-official:b:robot-vacuums' in p.get('category_ids',[]):
                target='robot-vacuum-body' if re.match(r'^DJI ROMO [PAS] \(',name,re.I) else 'robot-vacuum-parts'
                selected=['type:'+target];reason='dji-official-robot'
            elif re.match(r'^Osmo Nano \(',name,re.I):
                selected=['type:kpp:c020'];reason='dji-official-action-camera'
        # Subdivide known groups only. Accessory model names do not create bodies.
        ancestors=set(x for c in selected for x in path(c))
        refinements=[
          ('kpp:0710','mat-light',r'infinimat|인피니매트|라이트.*매트|매트.*라이트|LED.*매트'),('kpp:0710','mini-light',r'미니.*(?:조명|라이트)|(?:조명|라이트).*미니|\bMC\b|\bAce\b'),('kpp:0710','panel-light',r'패널|panel|nova'),('kpp:0710','tube-light',r'infinibar|인피니바|튜브|tube'),('kpp:06','car-mount',r'카마운팅|car\s*mount|차량.*마운트|car\s*rig'),
          ('kpp:0110','carbon',r'카본|carbon'),('kpp:0110','aluminum',r'알루미늄|alum'),('kpp:0110','mini-tripod',r'미니|mini|테이블|table'),('kpp:0110','travel-tripod',r'여행|travel'),
          ('kpp:0120','ball-head',r'볼\s*헤드|ball'),('kpp:0120','video-head',r'비디오|video|fluid'),('kpp:0120','gear-head',r'기어|gear'),('kpp:0120','gimbal-head',r'짐벌|gimbal'),('kpp:0120','pan-head',r'3.?way|파노라마|panoram'),
          ('kpp:0210','uv',r'\bUV\b|protect'),('kpp:0210','cpl',r'\bCPL\b|편광'),('kpp:0220','vnd',r'가변|variable|\bVND\b'),('kpp:0220','nd-pl',r'ND\s*[-/]?\s*PL'),('kpp:0230','mist',r'미스트|mist|소프트|soft'),
          ('kpp:0520','sling-bag',r'슬링|sling|크로스'),('kpp:0530','rolling-case',r'롤링|rolling|하드|hard'),
          ('kpp:0680','v-mount',r'V.?마운트|V.?mount|broadcast'),('kpp:0730','wireless-mic',r'무선|wireless|라크|lark'),
        ]
        for parent,target,pattern in refinements:
            if p['kind']=='rental' and target in {'mat-light','mini-light','panel-light','tube-light','car-mount'}:continue
            if 'type:'+parent in ancestors and re.search(pattern,name,re.I):selected.append('type:'+target)
        if 'type:kpp:0220' in ancestors and not any(x in selected for x in ('type:vnd','type:nd-pl')):selected.append('type:fixed-nd')
        if 'type:kpp:0680' in ancestors and 'type:v-mount' not in selected:selected.append('type:camera-battery')
        if p['id'] in (overrides or {}):selected=['type:'+x.removeprefix('type:') for x in overrides[p['id']]];reason='reviewed-override'
        assigned=list(dict.fromkeys(x for c in selected for x in path(c)))
        p['type_ids']=list(dict.fromkeys([c for c in p['type_ids'] if not c.startswith('type:')]+assigned))
        audit.append({'id':p['id'],'name':p['name'],'brand_id':bid,'reason':reason,'types':assigned})
    for cid in nodes:path(cid)
    # Stable depth-first order keeps dropdown parents beside their descendants.
    result=[]
    def walk(cid):
        result.append(nodes[cid])
        for child in nodes.values():
            if child['parent_id']==cid:walk(child['id'])
    for c in sorted((c for c in nodes.values() if c['parent_id'] is None),key=lambda c:order.get(c['id'][5:],999)):walk(c['id'])
    return result,{'category_count':len(result),'root_count':len(roots),'product_count':len(audit),'reasons':dict(Counter(x['reason'] for x in audit)),'assignments':audit}
