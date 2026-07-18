# -*- coding: utf-8 -*-
"""마스터 브랜드 레지스트리 생성 — rainbowshop(우리샵) 브랜드 ∪ 스크랩(clmedia/tilta) 브랜드, 중복 통합.
   출력: data/brands.json (canonical). 각 브랜드 1회, 소스표시 + 제품수."""
import sys, io, json, glob, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT=r"\\Nadaunproject\nadaunproject\_Site\nadaun-shop"
PDIR=ROOT+r"\data\products"

# rainbowshop 제품구매 브랜드 55 + 렌탈틸타 → (slug, 한글표기, 영문)
RAINBOW=[
("nisi","니시","NISI"),("pmi","피엠아이","PMI"),("captureone","캡쳐원","CAPTURE ONE"),("dji","디제이아이","DJI"),
("hoverair","호버에어","HOVER AIR"),("swit","스윗","SWIT"),("laowa","라오와","LAOWA"),("jackery","잭커리","JACKERY"),
("zgcine","지지씨","ZGCINE"),("aputure","어퓨처","APUTURE"),("harlowe","할로위","HARLOWE"),("nanlite","난라이트","NANLITE"),
("nanlux","난룩스","NANLUX"),("aurora","오로라","AURORA"),("profoto","프로포토","PROFOTO"),("peribounce","페리바운스","PERIBOUNCE"),
("pelican","펠리칸","PELICAN"),("tethertools","테더툴스","TETHERTOOLS"),("edelkrone","에델크론","EDELKRONE"),("sony","소니","SONY"),
("canon","캐논","CANON"),("fujifilm","후지필름","FUJIFILM"),("parabolix","파라볼릭스","PARABOLIX"),("tvlogic","티비로직","TVLogic"),
("eizo","에이조","EIZO"),("epson","엡손","EPSON"),("hollyland","홀리랜드","HOLLYLAND"),("motion9","모션9","MOTION9"),
("ifootage","아이풋티지","IFOOTAGE"),("smallrig","스몰리그","SMALLRIG"),("arcaswiss","아르카스위스","ARCA SWISS"),("sachtler","삭틀러","SACHTLER"),
("shure","슈어","SHURE"),("eimage","이이미지","E-IMAGE"),("leofoto","레오포토","LEOFOTO"),("gitzo","기트조","GITZO"),
("avenger","어벤져","AVENGER"),("matthews","매튜스","MATTHEWS"),("kupo","쿠포","KUPO"),("wacom","와콤","WACOM"),
("sedona","세도나","SEDONA"),("leefilters","리필터","LEE FILTERS"),("savage","새비지","SAVAGE"),("ragplace","래그플레이스","The Rag Place"),
("gentree","젠트리","GENTREE"),("sekonic","세코닉","SEKONIC"),("teris","테리스","TERIS"),("sennheiser","젠하이저","SENNHEISER"),
("blackmagic","블랙매직","BLACKMAGICDESIGN"),("robocup","로보컵","ROBO CUP"),("ecoflow","에코플로우","ECOFLOW"),("homan","호만","HOMAN"),
("livernovo","리버노보","LIVERNOVO"),("ricoh","리코","RICOH"),("tilta","틸타","TILTA"),
]
# 공급사 사이트(avx/plthink/hipixelplus/onnoff) 취급 브랜드 — 신규만 (slug,한글,영문)
SUPPLIER=[
("ursa","우르사","URSA"),("deity","데이티","Deity"),("portkeys","포트키즈","PortKeys"),("flowcine","플로우씬","FLOWCINE"),
("litra","리트라","Litra"),("cametv","카메티비","CAME-TV"),("vaxis","박시스","VAXIS"),("ulanzi","율란지","Ulanzi"),
("zeapon","제아폰","ZEAPON"),("coman","코만","COMAN"),("readyrig","레디릭","READYRIG"),("prograde","프로그레이드","PROGRADE"),
("neumann","노이만","NEUMANN"),("feelworld","필월드","FEELWORLD"),("movmax","무브맥스","MOVMAX"),("gripfilm","그립필름","gripfilm"),
("cinemadevices","시네마디바이스","CINEMA DEVICES"),("smartsystem","스마트시스템","SmartSystem"),("motocrane","모토크레인","MOTOCRANE"),
("pdmovie","피디무비","PDMOVIE"),("snorricam","스노리캠","SNORRICAM"),("manfrotto","맨프로토","Manfrotto"),("nodo","노도","NODO"),
("sandisk","샌디스크","SanDisk"),("startrc","스타트알씨","StartRC"),("healingshield","힐링쉴드","HealingShield"),("topping","토핑","TOPPING"),
("selens","셀렌즈","Selens"),("puas","퓨어스","PUAS"),("xvive","엑스바이브","Xvive"),("dearkol","디어콜","Dearkol"),
("accsoon","엑스순","ACCSOON"),("yconion","와이씨어니언","YC Onion"),("tarion","타리온","TARION"),("lexar","렉사","Lexar"),
("osee","오씨","OSEE"),("fookuspookus","푸쿠스푸쿠스","FOOKUS POOKUS"),("sakk","삭","SAKK"),("qfys","큐파이스","QFYS"),
("customeasy","커스텀이지","CUSTOM EASY"),("falcam","팔캠","FALCAM"),("valens","발렌스","VALENS"),("comica","코미카","Comica"),
("yololiv","욜로리브","YOLOLIV"),("gutek","구텍","GUTEK"),("libec","리벡","Libec"),("zhiyun","지윤","Zhiyun"),
("fotopro","포토프로","Fotopro"),("farseeing","파씨잉","Farseeing"),("plthink","플싱크","PLTHINK"),("dewfree","듀프리","DEWFREE"),
("compix","컴픽스","Compix"),("vinten","빈텐","Vinten"),("oconnor","오코너","OConnor"),("godox","고독스","GODOX"),
]
# 스크랩 slug → canonical slug (표기 통일)
ALIAS={"zgc":"zgcine"}
# 스크랩 slug → 한글표기(레인보우에 없던 브랜드용)
KR_EXTRA={"kase":"카세","arri":"아리","dzofilm":"디조필름","novachips":"노바칩스","qualite":"퀄라이트",
 "osram":"오스람","astera":"아스테라","artmu":"아트뮤","fxlion":"에프엑스리온","nitecore":"나이트코어",
 "samyang":"삼양","visgo":"비스고","typhoon":"타이포크","openmoon":"오픈문","rode":"로데","teradek":"테라덱",
 "atomos":"아토모스","desview":"데스뷰","edicam":"에디캠","cartello":"카텔로","alvin":"앨빈스케이블","noga":"노가",
 "pashing":"파싱","panasonic":"파나소닉","godox":"고독스","_custom":"주문제작","_misc":"기타"}

# 스크랩 제품수
scraped={}
for f in glob.glob(PDIR+r"\*.json"):
    slug=os.path.basename(f).replace(".json",""); slug=ALIAS.get(slug,slug)
    j=json.load(open(f,encoding="utf-8")); scraped[slug]=scraped.get(slug,0)+len(j.get("products",{}))

reg={}  # slug -> record
def touch(slug,kr,en):
    if slug not in reg:
        reg[slug]={"slug":slug,"kr":kr,"en":en,"in_rainbow":False,"in_supplier":False,"in_scrape":False,"count":0}
    return reg[slug]
for slug,kr,en in RAINBOW: touch(slug,kr,en)["in_rainbow"]=True
for slug,kr,en in SUPPLIER:
    r=touch(slug,kr,en); r["in_supplier"]=True
    if not r["kr"] or r["kr"]==slug: r["kr"]=kr
for slug,cnt in scraped.items():
    r=touch(slug,KR_EXTRA.get(slug,slug),slug.upper()); r["in_scrape"]=True; r["count"]=cnt

order=sorted(reg.values(), key=lambda r:(-r["count"], r["slug"]))
json.dump({"total":len(order),"brands":order}, open(ROOT+r"\data\brands.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

both=[r for r in order if r["in_rainbow"] and r["in_scrape"]]
rainonly=[r for r in order if r["in_rainbow"] and not r["in_scrape"]]
scrapeonly=[r for r in order if not r["in_rainbow"] and r["in_scrape"]]
print(f"마스터 브랜드 {len(order)}개 = rainbow {sum(1 for r in order if r['in_rainbow'])} ∪ scrape {len(scraped)} (중복통합)")
print(f"\n■ 양쪽 다 있음(겹침) {len(both)}개 — 제품 스크랩 완료:")
for r in both: print(f"   {r['kr']}({r['en']}) {r['count']}개")
print(f"\n■ rainbow에만 있음 {len(rainonly)}개 — 아직 제품 스크랩 안됨(나중에):")
print("   "+", ".join(f"{r['kr']}({r['en']})" for r in rainonly))
print(f"\n■ 스크랩에만 있음 {len(scrapeonly)}개 — rainbow에 없던 신규:")
print("   "+", ".join(f"{r['kr']}" for r in scrapeonly))
print("\n→ data/brands.json 저장")
