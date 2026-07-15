# -*- coding: utf-8 -*-
"""공용 브랜드 매핑 — 상품명 접두 → (한글표기, slug). 모든 신규 스크래퍼가 import.
   kpp.py BRANDS 기반 + _브랜드_리스트업.txt 신규 브랜드 추가 (2026-07-09).
   미매칭 → ("_기타","_misc") — silent drop 금지, 대표 육안검수에서 보정."""
import re

BRANDS = [
 # 기존 (kpp.py 동일)
 ("스몰리그","smallrig"),("SmallRig","smallrig"),("틸타","tilta"),("Tilta","tilta"),
 ("레오포토","leofoto"),("Leofoto","leofoto"),("어퓨처","aputure"),("어퓨쳐","aputure"),("아마란","aputure"),
 ("아리","arri"),("홀리랜드","hollyland"),("난라이트","nanlite"),("난룩스","nanlux"),("프로포토","profoto"),
 ("소니","sony"),("캐논","canon"),("니콘","nikon"),("후지","fujifilm"),("파나소닉","panasonic"),
 ("디제이아이","dji"),("DJI","dji"),("라오와","laowa"),("젠하이저","sennheiser"),("슈어","shure"),
 ("니시","nisi"),("NISI","nisi"),("NiSi","nisi"),("쿠포","kupo"),("젠트리","gentree"),("이지리그","easyrig"),
 ("맨프로토","manfrotto"),("삭틀러","sachtler"),("자이스","zeiss"),("블랙매직","blackmagic"),
 ("호크우드","hawkwood"),("모션9","motion9"),("모션나인","motion9"),("노바칩스","novachips"),("기트조","gitzo"),
 ("퀄라이트","qualite"),("오스람","osram"),("잭커리","jackery"),("아스테라","astera"),
 ("에프엑스리온","fxlion"),("FXLION","fxlion"),("나이트코어","nitecore"),("아트뮤","artmu"),
 ("ZGCINE","zgcine"),("ZGC","zgcine"),("고독스","godox"),("웨스캇","westcott"),("브레스","broncolor"),
 ("디조필름","dzofilm"),("디죠필름","dzofilm"),("디죠","dzofilm"),("조프","dzofilm"),
 ("카세","kase"),("비스고","visgo"),("티비로직","tvlogic"),("TVLogic","tvlogic"),("타이포크","typhoon"),("오픈문","openmoon"),
 ("로데","rode"),("삼양","samyang"),("테라덱","teradek"),("에디캠","edicam"),("어벤져","avenger"),
 ("데스뷰","desview"),("로보컵","robocup"),("줌","zoom"),("카텔로","cartello"),("아이풋티지","ifootage"),
 ("아토모스","atomos"),("프로게퍼","progaffer"),("앨빈스케이블","alvin"),("노가","noga"),
 ("호야","hoya"),("HOYA","hoya"),("토키나","tokina"),("TOKINA","tokina"),
 ("빌트록스","viltrox"),("VILTROX","viltrox"),("피지테크","pgytech"),("PGYTECH","pgytech"),
 ("티티아티산","ttartisan"),("TTArtisan","ttartisan"),("완더드","wandrd"),("WANDRD","wandrd"),
 ("지테이","zitay"),("ZITAY","zitay"),("아스트호리","astrhori"),("ASTRHORI","astrhori"),
 ("에이치앤와이","hy"),("H&Y","hy"),("맷세스","matthews"),("매튜스","matthews"),("아르카스위스","arcaswiss"),
 ("파싱","pashing"),("[주문제작]","_custom"),("주문제작","_custom"),
 # 신규 소스 브랜드 (_브랜드_리스트업.txt 2026-07-07)
 ("슈페리어","superior"),("Superior","superior"),("포멕스","fomex"),("Fomex","fomex"),
 ("벤로","benro"),("Benro","benro"),("BENRO","benro"),
 ("리벡","libec"),("Libec","libec"),("LIBEC","libec"),
 ("제네렉","genelec"),("Genelec","genelec"),("GENELEC","genelec"),
 ("아투리아","arturia"),("Arturia","arturia"),("ARTURIA","arturia"),
 ("아포지","apogee"),("Apogee","apogee"),("APOGEE","apogee"),
 ("데이터컬러","datacolor"),("Datacolor","datacolor"),("스파이더","datacolor"),("Spyder","datacolor"),
 ("세코닉","sekonic"),("Sekonic","sekonic"),("SEKONIC","sekonic"),
 ("페리바운스","peribounce"),("PERIBOUNCE","peribounce"),
 ("펠리컨","pelican"),("펠리칸","pelican"),("Pelican","pelican"),("PELICAN","pelican"),
 ("발렌스","valens"),("VALENS","valens"),
 ("셔틀러","shuttler"),("Shuttler","shuttler"),
 ("테더툴스","tethertools"),("TetherTools","tethertools"),("Tether Tools","tethertools"),
 ("파라볼릭스","parabolix"),("Parabolix","parabolix"),
 ("스윗","swit"),("SWIT","swit"),("호버에어","hoverair"),("HOVER","hoverair"),
 ("에델크론","edelkrone"),("edelkrone","edelkrone"),("캡쳐원","captureone"),("캡처원","captureone"),
 ("에이조","eizo"),("EIZO","eizo"),("엡손","epson"),("EPSON","epson"),
 ("와콤","wacom"),("Wacom","wacom"),("세도나","sedona"),("SEDONA","sedona"),
 ("리필터","leefilters"),("LEE","leefilters"),("새비지","savage"),("Savage","savage"),
 ("래그플레이스","ragplace"),("테리스","teris"),("TERIS","teris"),("이이미지","eimage"),("E-IMAGE","eimage"),
 ("에코플로우","ecoflow"),("ECOFLOW","ecoflow"),("할로위","harlowe"),("Harlowe","harlowe"),
 ("오로라","aurora"),("피엠아이","pmi"),("PMI","pmi"),("스위프트","swift"),
 ("시그마","sigma"),("SIGMA","sigma"),("라이카","leica"),("핫셀블라드","hasselblad"),
 ("탐론","tamron"),("TAMRON","tamron"),("올림푸스","olympus"),("OM시스템","omsystem"),
 ("바투","vatue"),("리코","ricoh"),("RICOH","ricoh"),("호만","homan"),("리버노보","livernovo"),
 # 포멕스 취급 추가 브랜드 (2026-07-09 NAV 확인)
 ("사라모닉","saramonic"),("Saramonic","saramonic"),("엘가토","elgato"),("Elgato","elgato"),
 ("프리소너스","presonus"),("PreSonus","presonus"),("마샬","marshall"),("Marshall","marshall"),
 ("카토니","cartoni"),("Cartoni","cartoni"),("뱅가드","vanguard"),("Vanguard","vanguard"),
 ("아이릭스","irix"),("Irix","irix"),("XEEN","xeen"),("씬 ","xeen"),("IDX","idx"),
 ("베일런","beillen"),("BEILLEN","beillen"),("타스캠","tascam"),("타스켐","tascam"),("tascam","tascam"),
 ("텐바","tenba"),("TENBA","tenba"),("SKB","skb"),("본 ","bon"),("BON","bon"),("이보토","evoto"),("evoto","evoto"),
 # _misc 감사 보강 (2026-07-11): 기존 브랜드 영문/표기변형 + 신규 브랜드
 ("KUPO","kupo"),("Kupo","kupo"),("맨프로또","manfrotto"),("Manfrotto","manfrotto"),("MANFROTTO","manfrotto"),
 ("Blackmagic","blackmagic"),("BLACKMAGIC","blackmagic"),("GITZO","gitzo"),("Gitzo","gitzo"),("짓조","gitzo"),
 ("MATTHEWS","matthews"),("Matthews","matthews"),("메튜","matthews"),("SHURE","shure"),("Shure","shure"),
 ("GODOX","godox"),("Godox","godox"),("사베지","savage"),("SAVAGE","savage"),("에스케이비","skb"),
 ("아스트로호리","astrhori"),("HNY","hy"),("더래그플레이스","ragplace"),
 ("B+W","bw"),("비더블유","bw"),("씽크탱크","thinktank"),("TTP","thinktank"),("ThinkTank","thinktank"),
 ("FALCAM","falcam"),("팔캠","falcam"),("프리즘 렌즈","prismlensfx"),("PRISM LENS","prismlensfx"),
 ("MEKING","meking"),("머킹","meking"),("SCHNEIDER","schneider"),("슈나이더","schneider"),
 ("COMICA","comica"),("코미카","comica"),("금광","kumkwang"),("Kumkwang","kumkwang"),("KUMKWANG","kumkwang"),
 ("ZEAPON","zeapon"),("지폰","zeapon"),("ULANZI","ulanzi"),("울란지","ulanzi"),
 ("ZHIYUN","zhiyun"),("지윤","zhiyun"),("LUXPAD","luxpad"),("룩스패드","luxpad"),
 ("ROCKNROLLER","rocknroller"),("락앤롤러","rocknroller"),("PANYANFILM","panyanfilm"),("판얀필름","panyanfilm"),
 ("KLOTZ","klotz"),("클로츠","klotz"),
 # _misc 2차 감사 보강 (2026-07-15): 후반 소스(ldnet/cinemall/bando) 유입분
 ("Canon","canon"),("CANON","canon"),("Sony","sony"),("SONY","sony"),("ARRI","arri"),("Arri","arri"),
 ("Hasselblad","hasselblad"),("HASSELBLAD","hasselblad"),("Broncolor","broncolor"),("BRONCOLOR","broncolor"),
 ("WOTANCRAFT","wotancraft"),("보탄크래프트","wotancraft"),("Oberwerth","oberwerth"),("OBERWERTH","oberwerth"),
 ("BRIESE","briese"),("브리제","briese"),("Leitz","leitz"),("LEITZ","leitz"),
 ("Lexar","lexar"),("LEXAR","lexar"),("렉사","lexar"),("두릭스","durix"),("Durix","durix"),
 ("하네뮬레","hahnemuhle"),("Hahnemuhle","hahnemuhle"),("Giottos","giottos"),("지오토스","giottos"),
 ("PDMOVIE","pdmovie"),("피디무비","pdmovie"),("PDmovie","pdmovie"),
 ("cmotion","cmotion"),("CMOTION","cmotion"),("씨모션","cmotion"),
]

def brand_of(name):
    """상품명 → (한글표기, slug). 앞 [신품]/[재고보유] 태그 제거 후 접두 매칭.
       접두 미매칭이면 선두 [태그] 내용도 브랜드로 시도 (hktools식 [B+W] 표기 대응,
       [렌탈]/[HK위탁] 같은 비브랜드 태그는 BRANDS에 없어 자동 통과)."""
    n0 = (name or "").strip()
    lead = re.match(r"^(?:\[[^\]]*\]\s*)+", n0)
    tags = re.findall(r"\[([^\]]+)\]", lead.group(0)) if lead else []
    n = n0[lead.end():].strip() if lead else n0
    nn = n.replace(" ", "")
    for ko, slug in BRANDS:
        if n.startswith(ko) or nn.startswith(ko.replace(" ", "")):
            return ko, slug
    for t in tags:
        tt = t.replace(" ", "").upper()
        for ko, slug in BRANDS:
            kk = ko.replace(" ", "").upper()
            if tt == kk or tt.startswith(kk):
                return ko, slug
    return "_기타", "_misc"
