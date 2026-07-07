# -*- coding: utf-8 -*-
"""[메인 카탈로그] data/products/*.json + data/brands.json → catalog.html.
   브랜드 우선(우리사이트처럼): 브랜드 디렉토리 → 브랜드 클릭 시 그 브랜드의 대>중>소 명확 표시.
   모든 제품·브랜드 노출이 1순위. 카테고리 우선 브라우징은 build_catalog_category.py(후속)."""
import sys, io, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import kpp_classify as K
import tilta_taxonomy as TT
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(r"\\Nadaunproject\nadaunproject\_DAVINCI NADAUN PROJECT\_Site\nadaun-shop")
DATA = ROOT/"data"/"products"

# ── 마스터 브랜드(전체 138) ──
master = json.load(open(ROOT/"data"/"brands.json", encoding="utf-8"))["brands"]
by_slug = {m["slug"]: m for m in master}

# ── 제품 로드 + 분류(브랜드별 taxonomy override) + 슬러그 태깅 ──
# 틸타=tilta.com 자체 트리(카메라별/제품군, 소=모델). 그 외=KPP 대>중(소 없음).
prods=[]
for f in sorted(DATA.glob("*.json")):
    if f.stem=="_index": continue
    d=json.load(open(f,encoding="utf-8"))
    top_slug=d.get("brand_slug") or f.stem
    for p in d.get("products",{}).values():
        slug=p.get("brand_slug") or top_slug
        nm=p.get("name",""); cat=p.get("category","")
        if slug=="tilta":
            dc,dn,jc,jn,kc,kn = TT.classify_tilta(nm,cat)
        else:
            dc,dn,jc,jn = K.classify(nm,cat); kc,kn = "",""
        price=p.get("price",0); usd=p.get("price_usd",0)
        prods.append({"s":slug,"b":p.get("brand",""),"n":nm,"id":p["id"],
                      "d":dc,"dn":dn,"j":jc,"jn":jn,"k":kc,"kn":kn,"p":price,"usd":usd,
                      "t":p["images"].get("thumb","")})

# 대분류 통합 순서: 틸타(카메라별→제품군→특가) + KPP. 코드 disjoint.
DAE_ORDER_ALL = TT.DAE_ORDER + K.DAE_ORDER
DAE_NAME_ALL = {**TT.DAE, **K.DAE}
dorder={c:i for i,c in enumerate(DAE_ORDER_ALL)}

from collections import Counter, defaultdict
cnt=Counter(p["s"] for p in prods)
# 그룹 카운트(브랜드별 중/소) → 그리드 그룹 정렬용
jc_cnt=Counter((p["s"],p["d"],p["j"]) for p in prods)
kc_cnt=Counter((p["s"],p["d"],p["j"],p["k"]) for p in prods)
prods.sort(key=lambda c:(dorder.get(c["d"],99),
                         -jc_cnt[(c["s"],c["d"],c["j"])], c["jn"],
                         -kc_cnt[(c["s"],c["d"],c["j"],c["k"])], c["kn"],
                         -(c["p"] or c["usd"] or 0)))
# 브랜드 대표이미지 = 슬러그별 첫 썸네일
bimg={}
for p in prods:
    if p["s"] not in bimg and p["t"]: bimg[p["s"]]=p["t"]

# ── 브랜드 디렉토리(제품보유 + 마스터 전체) ──
FRIENDLY={"_misc":("기타","ETC"),"_custom":("주문제작","CUSTOM")}
slugs=set(cnt)|set(by_slug)
brands=[]
for s in slugs:
    m=by_slug.get(s,{})
    kr=m.get("kr") or FRIENDLY.get(s,("",""))[0]
    en=m.get("en") or FRIENDLY.get(s,("",s.upper()))[1] or s.upper()
    # 제품쪽 kr 이름 보정(마스터 미스매치 시 제품 brand 사용)
    if not kr:
        pk=next((p["b"] for p in prods if p["s"]==s and p["b"]),"")
        kr=pk or en
    brands.append({"s":s,"en":en,"kr":kr,"n":cnt.get(s,0),
                   "img":bimg.get(s,""),"r":bool(m.get("in_rainbow"))})
# 정렬: 제품보유 많은 순 → 나머지 알파벳
brands.sort(key=lambda b:(-b["n"], b["en"].lower()))
have=sum(1 for b in brands if b["n"]>0)
print(f"제품 {len(prods)} / 브랜드 총 {len(brands)}(제품보유 {have}) / 대분류 {len({p['d'] for p in prods})}")

DATAJS=json.dumps(prods,ensure_ascii=False,separators=(",",":"))
BRANDSJS=json.dumps(brands,ensure_ascii=False,separators=(",",":"))
DAEORDER=json.dumps(DAE_ORDER_ALL)
DAENAME=json.dumps(DAE_NAME_ALL,ensure_ascii=False)

HTML="""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/><title>나다운 스페이스 — 브랜드 카탈로그</title>
<meta name="description" content="촬영장비 브랜드 카탈로그 — Tilta·DJI·SONY·Aputure·NANLITE 등 브랜드별 3,400+ 제품 렌탈·구매. 서울 영등포 나다운 스페이스 (레인보우베네)."/>
<meta name="keywords" content="촬영장비 카탈로그, 브랜드별 촬영장비, Tilta, DJI, 소니, 카메라 렌탈, 렌즈, 짐벌, 조명, 나다운 스페이스"/>
<meta name="robots" content="index, follow, max-image-preview:large"/>
<link rel="canonical" href="https://shop.nadaun.co/catalog.html"/>
<meta property="og:type" content="website"/>
<meta property="og:site_name" content="나다운 스페이스"/>
<meta property="og:title" content="나다운 스페이스 — 브랜드 카탈로그"/>
<meta property="og:description" content="브랜드별 3,400+ 촬영장비 렌탈·구매. 영등포 나다운 스페이스."/>
<meta property="og:url" content="https://shop.nadaun.co/catalog.html"/>
<link rel="icon" href="brand/favicon.ico"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css"/>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--ink:#141414;--soft:#6b6b6b;--line:#e7e5e0;--gold:#b78a47;--navy:#1b2a4a;--cream:#f6f4f0;--ease:cubic-bezier(.16,1,.3,1)}
body{font-family:Pretendard,system-ui,sans-serif;color:var(--ink);background:#fff;-webkit-font-smoothing:antialiased}
.wrap{max-width:1400px;margin:0 auto;padding:0 clamp(14px,3.5vw,44px)}
header{border-bottom:1px solid var(--line);position:sticky;top:0;background:rgba(255,255,255,.94);backdrop-filter:blur(12px);z-index:30}
.nav{display:flex;align-items:center;justify-content:space-between;height:62px}.nav img.logo{height:19px}
.nav a.home{font-size:13px;color:var(--soft)}
a{text-decoration:none;color:inherit}
/* ── 페이지 인트로 ── */
.intro{padding:clamp(28px,5vw,54px) 0 20px}
.intro .idx{font-size:12px;letter-spacing:.24em;color:var(--gold);text-transform:uppercase;font-weight:700;margin-bottom:12px}
.intro h1{font-size:clamp(26px,4vw,40px);font-weight:800;letter-spacing:-.03em;line-height:1.08}
.intro p{color:var(--soft);margin-top:12px;font-size:14.5px}
.tools{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-top:22px}
.bsearch{border:1px solid var(--line);border-radius:999px;padding:11px 18px;font-size:14px;font-family:inherit;background:#fff;width:min(320px,70vw)}
.seg{display:flex;border:1px solid var(--line);border-radius:999px;overflow:hidden}
.seg button{border:0;background:#fff;padding:10px 16px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;color:var(--soft)}
.seg button.on{background:var(--navy);color:#fff}
.link-cat{margin-left:auto;font-size:13px;color:var(--soft);border-bottom:1px solid var(--line);padding-bottom:2px}
.link-cat:hover{color:var(--ink);border-color:var(--gold)}
/* ── 브랜드 그리드 ── */
.bgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px;padding:8px 0 80px}
.bcard{border:1px solid var(--line);border-radius:16px;padding:22px 20px;display:flex;flex-direction:column;gap:14px;cursor:pointer;transition:.45s var(--ease);background:#fff;min-height:150px}
.bcard:hover{transform:translateY(-4px);box-shadow:0 16px 36px rgba(20,20,20,.09);border-color:var(--navy)}
.bcard.soon{cursor:default;opacity:.62}
.bcard.soon:hover{transform:none;box-shadow:none;border-color:var(--line)}
.bcard .logo{height:46px;display:flex;align-items:center}
.bcard .logo img{max-height:46px;max-width:120px;object-fit:contain;mix-blend-mode:multiply}
.bcard .logo .ini{width:46px;height:46px;border-radius:12px;background:var(--cream);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:20px;color:var(--navy)}
.bcard .en{font-size:17px;font-weight:800;letter-spacing:-.01em}
.bcard .kr{font-size:13px;color:var(--soft);margin-top:2px}
.bcard .meta{margin-top:auto;display:flex;align-items:center;justify-content:space-between}
.bcard .cnt{font-size:13px;font-weight:700;color:var(--navy)}
.bcard .cnt.soon{color:var(--soft);font-weight:600}
.bcard .arw{font-size:15px;color:var(--gold);transition:transform .5s var(--ease)}
.bcard:hover .arw{transform:translate(4px,-4px)}
/* ── 브랜드 상세 ── */
.detail{display:none}
.detail.on{display:block}
.dir.off{display:none}
.crumb{display:flex;align-items:center;gap:10px;padding:22px 0 4px;font-size:13px;color:var(--soft)}
.crumb a:hover{color:var(--ink)}
.dhead{display:flex;align-items:center;gap:20px;padding:12px 0 22px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.dhead .logo{height:52px;display:flex;align-items:center}
.dhead .logo img{max-height:52px;max-width:150px;object-fit:contain;mix-blend-mode:multiply}
.dhead .logo .ini{width:52px;height:52px;border-radius:13px;background:var(--cream);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:23px;color:var(--navy)}
.dhead .tt .en{font-size:26px;font-weight:800;letter-spacing:-.02em}
.dhead .tt .kr{font-size:14px;color:var(--soft);margin-top:2px}
.dhead .dcnt{margin-left:auto;font-size:14px;color:var(--soft)}.dhead .dcnt b{color:var(--ink);font-weight:800;font-size:17px}
/* 대분류 탭 + 중분류 칩 */
.daebar{position:sticky;top:62px;background:rgba(255,255,255,.96);backdrop-filter:blur(10px);z-index:20;padding:12px 0 10px;border-bottom:1px solid var(--line)}
.daes{display:flex;flex-wrap:wrap;gap:7px}
.daes button{border:1px solid var(--line);background:#fff;border-radius:9px;padding:8px 14px;font-size:13.5px;font-weight:700;letter-spacing:-.01em;cursor:pointer;transition:.3s var(--ease);font-family:inherit}
.daes button:hover{border-color:var(--navy)}
.daes button.on{background:var(--navy);color:#fff;border-color:var(--navy)}
.daes button .c{opacity:.55;font-weight:600;margin-left:5px;font-size:12px}.daes button.on .c{opacity:.8}
.jungbar{background:var(--cream);border-bottom:1px solid var(--line);overflow:hidden;max-height:0;transition:max-height .45s var(--ease)}
.jungbar .in{padding:11px 0}
.jungs{display:flex;flex-wrap:wrap;gap:6px}
.jungs button{border:1px solid var(--line);background:#fff;border-radius:999px;padding:6px 13px;font-size:12.5px;font-weight:600;cursor:pointer;transition:.3s var(--ease);font-family:inherit}
.jungs button:hover{border-color:var(--gold)}
.jungs button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.jungs button .c{opacity:.5;margin-left:4px}
.count{padding:16px 0 8px;font-size:13px;color:var(--soft)}.count b{color:var(--ink);font-weight:700}
.gridflow{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:20px 16px;padding-bottom:16px}
.ghead{grid-column:1/-1;font-size:18px;font-weight:800;letter-spacing:-.02em;margin:24px 0 2px;display:flex;align-items:baseline;gap:9px}
.ghead .gc{font-size:12.5px;font-weight:600;color:var(--soft)}
.jhead{grid-column:1/-1;font-size:14px;font-weight:700;color:var(--navy);margin:14px 0 2px;padding-bottom:8px;border-bottom:1.5px solid var(--line);display:flex;align-items:baseline;gap:8px}
.jhead .jc{font-size:12px;font-weight:600;color:var(--soft)}
.khead{grid-column:1/-1;font-size:12.5px;font-weight:700;color:var(--ink);margin:8px 0 0;display:flex;align-items:baseline;gap:7px}
.khead::before{content:"";width:5px;height:5px;border-radius:50%;background:var(--gold);display:inline-block}
.khead .kc{font-size:11px;font-weight:600;color:var(--soft)}
.card{border:1px solid var(--line);border-radius:13px;overflow:hidden;display:flex;flex-direction:column;transition:.4s var(--ease);background:#fff}
.card:hover{transform:translateY(-4px);box-shadow:0 14px 32px rgba(20,20,20,.09)}
.card .ph{aspect-ratio:1;background:var(--cream);overflow:hidden;display:flex;align-items:center;justify-content:center}
.card .ph img{width:100%;height:100%;object-fit:contain;mix-blend-mode:multiply}
.card .ph .no{color:#c9c6bf;font-size:12px}
.card .b{padding:12px 13px 15px}
.card .bt{font-size:10.5px;font-weight:700;letter-spacing:.03em;color:var(--gold);text-transform:uppercase}
.card .nm{font-size:13px;font-weight:500;line-height:1.4;margin:6px 0 9px;height:2.8em;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.card .pr{font-size:15.5px;font-weight:800;letter-spacing:-.02em}
.card .pr small{font-size:12px;font-weight:500;color:var(--soft)}
.more{display:block;margin:14px auto 80px;border:1px solid var(--ink);background:#fff;border-radius:999px;padding:13px 34px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}
.empty{padding:60px 0 90px;text-align:center;color:var(--soft);font-size:14px}
@media(max-width:600px){.dhead .dcnt{margin-left:0;width:100%}}
</style></head><body>
<header><div class="wrap nav"><a href="index.html"><img class="logo" src="brand/logo-black.png" alt="nadaun"/></a><a class="home" href="index.html">← 홈</a></div></header>

<!-- 브랜드 디렉토리 -->
<div class="wrap dir" id="dir">
  <div class="intro">
    <div class="idx">Brands</div>
    <h1>브랜드로 만나는 촬영장비</h1>
    <p id="introp">브랜드를 선택하면 카메라·삼각대·필터·렌즈 등 카테고리별로 정리된 제품을 볼 수 있습니다.</p>
    <div class="tools">
      <input class="bsearch" id="bsearch" placeholder="브랜드 검색 (예: 틸타, TILTA, SONY)…"/>
      <div class="seg"><button data-v="have" class="on" id="segHave">제품보유</button><button data-v="all" id="segAll">전체 브랜드</button></div>
      <a class="link-cat" href="catalog_category.html">카테고리로 보기 →</a>
    </div>
  </div>
  <div class="bgrid" id="bgrid"></div>
</div>

<!-- 브랜드 상세 -->
<div class="detail" id="detail">
  <div class="wrap"><div class="crumb"><a href="#" id="back">← 전체 브랜드</a></div>
    <div class="dhead" id="dhead"></div></div>
  <div class="daebar"><div class="wrap daes" id="daes"></div></div>
  <div class="jungbar" id="jungbar"><div class="wrap in"><div class="jungs" id="jungs"></div></div></div>
  <div class="wrap">
    <div class="count" id="count"></div>
    <div class="gridflow" id="grid"></div>
    <button class="more" id="more" style="display:none">더 보기</button>
  </div>
</div>

<script>
const DATA=__DATA__, BRANDS=__BRANDS__, DAEORDER=__DAEORDER__, DAENAME=__DAENAME__, PAGE=60;
const $=id=>document.getElementById(id);
const esc=s=>(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const fmt=d=>d.p>0?d.p.toLocaleString('ko-KR')+'원':(d.usd>0?'$'+d.usd+' <small>(원화예정)</small>':'가격문의');
const bmap={};BRANDS.forEach(b=>bmap[b.s]=b);
let segV='have',curSlug=null,curD='전체',curJ='전체',shown=PAGE;

/* ── 브랜드 디렉토리 ── */
function logoHTML(b,big){return b.img?`<img src="${b.img}" loading="lazy" alt="${esc(b.en)}">`:`<span class="ini">${esc((b.en||'?')[0])}</span>`}
function renderDir(q){
  q=(q||'').trim().toLowerCase();
  let list=BRANDS.filter(b=> segV==='all' || b.n>0 );
  if(q) list=list.filter(b=>b.en.toLowerCase().includes(q)||(b.kr||'').toLowerCase().includes(q)||b.s.includes(q));
  $('bgrid').innerHTML = list.length? list.map(b=>{
    const soon=b.n===0;
    return `<div class="bcard${soon?' soon':''}" ${soon?'':`data-s="${b.s}"`}>
      <div class="logo">${logoHTML(b)}</div>
      <div><div class="en">${esc(b.en)}</div>${b.kr?`<div class="kr">${esc(b.kr)}</div>`:''}</div>
      <div class="meta"><span class="cnt${soon?' soon':''}">${soon?'제품 준비중':b.n.toLocaleString()+'개 제품'}</span>${soon?'':'<span class="arw">↗</span>'}</div>
    </div>`}).join('') : '<div class="empty">해당 브랜드가 없습니다.</div>';
  $('bgrid').querySelectorAll('.bcard[data-s]').forEach(c=>c.onclick=()=>openBrand(c.dataset.s));
}

/* ── 브랜드 상세 ── */
function brandProds(){return DATA.filter(p=>p.s===curSlug)}
function pool(){return brandProds()} // 대/중 카운트용(브랜드 고정)
function filtered(){return pool().filter(p=>(curD==='전체'||p.d===curD)&&(curJ==='전체'||p.j===curJ))}
function renderHead(){
  const b=bmap[curSlug]||{en:curSlug,kr:'',img:''};const n=brandProds().length;
  $('dhead').innerHTML=`<div class="logo">${logoHTML(b)}</div>
    <div class="tt"><div class="en">${esc(b.en)}</div>${b.kr?`<div class="kr">${esc(b.kr)}</div>`:''}</div>
    <div class="dcnt"><b>${n.toLocaleString()}</b>개 제품</div>`;
}
function renderDaes(){
  const p=pool();const dc={};p.forEach(x=>dc[x.d]=(dc[x.d]||0)+1);
  const order=DAEORDER.filter(c=>dc[c]);
  $('daes').innerHTML=`<button data-d="전체" class="${curD==='전체'?'on':''}">전체<span class="c">${p.length}</span></button>`+
    order.map(c=>`<button data-d="${c}" class="${curD===c?'on':''}">${DAENAME[c]}<span class="c">${dc[c]}</span></button>`).join('');
  $('daes').querySelectorAll('button').forEach(x=>x.onclick=()=>{curD=x.dataset.d;curJ='전체';shown=PAGE;renderDetail()});
}
function renderJungs(){
  const bar=$('jungbar');
  if(curD==='전체'){bar.style.maxHeight='0';$('jungs').innerHTML='';return}
  const p=pool().filter(x=>x.d===curD);const jc={},jn={};p.forEach(x=>{jc[x.j]=(jc[x.j]||0)+1;jn[x.j]=x.jn});
  const order=Object.keys(jc).sort((a,b)=>jc[b]-jc[a]);
  $('jungs').innerHTML=`<button data-j="전체" class="${curJ==='전체'?'on':''}">전체<span class="c">${p.length}</span></button>`+
    order.map(j=>`<button data-j="${j}" class="${curJ===j?'on':''}">${esc(jn[j])}<span class="c">${jc[j]}</span></button>`).join('');
  bar.style.maxHeight='260px';
  $('jungs').querySelectorAll('button').forEach(x=>x.onclick=()=>{curJ=x.dataset.j;shown=PAGE;renderDetail()});
}
function card(d){return `<a class="card" href="/product/${d.s}/${d.id}.html">
  <div class="ph">${d.t?`<img src="${d.t}" loading="lazy" alt="">`:'<span class="no">이미지 준비중</span>'}</div>
  <div class="b"><div class="bt">${esc(d.jn)}</div><div class="nm">${esc(d.n)}</div><div class="pr">${fmt(d)}</div></div></a>`}
function renderDetail(){
  renderHead();renderDaes();renderJungs();
  const list=filtered();
  const lab=(curD!=='전체'?` · ${DAENAME[curD]}`:'')+(curJ!=='전체'&&list[0]?` · ${esc(list[0].jn)}`:'');
  $('count').innerHTML=`<b>${list.length.toLocaleString()}</b>개 제품${lab}`;
  // 대/중/소 카운트 + 그룹 헤더 (틸타=3단, 그 외=2단·소 없음)
  const dc={},jc={},kc={};
  list.forEach(x=>{dc[x.d]=(dc[x.d]||0)+1;jc[x.d+'|'+x.j]=(jc[x.d+'|'+x.j]||0)+1;kc[x.d+'|'+x.j+'|'+x.k]=(kc[x.d+'|'+x.j+'|'+x.k]||0)+1});
  const showD = curD==='전체', showJ = curJ==='전체', showK = curD!=='전체';
  let html='',lastD=null,lastJ=null,lastK=null;
  list.slice(0,shown).forEach(d=>{
    if(showD&&d.d!==lastD){lastD=d.d;lastJ=null;lastK=null;
      html+=`<div class="ghead">${DAENAME[d.d]} <span class="gc">${dc[d.d]}</span></div>`}
    if(showJ&&d.j!==lastJ){lastJ=d.j;lastK=null;
      html+=`<div class="jhead">${esc(d.jn)} <span class="jc">${jc[d.d+'|'+d.j]}</span></div>`}
    if(showK&&d.k&&d.k!==lastK){lastK=d.k;
      html+=`<div class="khead">${esc(d.kn)} <span class="kc">${kc[d.d+'|'+d.j+'|'+d.k]}</span></div>`}
    html+=card(d);
  });
  $('grid').innerHTML=html||'<div class="empty">해당 조건의 제품이 없습니다.</div>';
  $('more').style.display=list.length>shown?'block':'none';
}
function openBrand(s){
  curSlug=s;curD='전체';curJ='전체';shown=PAGE;
  $('dir').classList.add('off');$('detail').classList.add('on');
  window.scrollTo(0,0);history.replaceState(null,'','#'+s);renderDetail();
}
function closeBrand(){
  $('detail').classList.remove('on');$('dir').classList.remove('off');
  history.replaceState(null,'','#');window.scrollTo(0,0);
}
$('more').onclick=()=>{shown+=PAGE;renderDetail()};
$('back').onclick=e=>{e.preventDefault();closeBrand()};
$('bsearch').oninput=e=>renderDir(e.target.value);
$('segHave').onclick=()=>{segV='have';$('segHave').classList.add('on');$('segAll').classList.remove('on');renderDir($('bsearch').value)};
$('segAll').onclick=()=>{segV='all';$('segAll').classList.add('on');$('segHave').classList.remove('on');renderDir($('bsearch').value)};
addEventListener('hashchange',()=>{const s=location.hash.slice(1);if(s&&bmap[s])openBrand(s);else closeBrand()});
// 초기: 해시로 브랜드 직접진입 지원
renderDir('');
const h=location.hash.slice(1);
if(h&&bmap[h]&&bmap[h].n>0)openBrand(h);
</script></body></html>"""
out=(HTML.replace("__DATA__",DATAJS).replace("__BRANDS__",BRANDSJS)
         .replace("__DAEORDER__",DAEORDER).replace("__DAENAME__",DAENAME))
(ROOT/"catalog.html").write_text(out,encoding="utf-8")
print("→ catalog.html 생성", f"({len(out)//1024}KB)")
