# -*- coding: utf-8 -*-
"""[후속 카탈로그] data/products/*.json → catalog_category.html.
   카테고리(대분류) 우선 브라우징: [브랜드] + [대분류 탭] + [중분류 칩]. KPP 대>중>소(kpp_classify.py).
   ※ 메인은 브랜드 우선 build_catalog.py(catalog.html). 이건 별도 후속용."""
import sys, io, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import kpp_classify as K
import source_rules as SR
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(r"\\Nadaunproject\nadaunproject\_DAVINCI NADAUN PROJECT\_Site\nadaun-shop")
DATA = ROOT/"data"/"products"
SRC_IDX = SR.build_index(DATA)

prods=[]
for f in sorted(DATA.glob("*.json")):
    if f.stem=="_index": continue
    d=json.load(open(f,encoding="utf-8"))
    for p in d.get("products",{}).values():
        if not SR.allowed(p, p.get("brand_slug") or f.stem, SRC_IDX): continue
        prods.append(p)

cards=[]
for p in prods:
    if p.get("source")=="kpp" and p.get("ca_id"):     # KPP 정식분류가 정답 (이름추측 금지)
        dc,dn,jc,jn = K.from_ca_id(p["ca_id"], p.get("name",""), p.get("category",""))
    else:
        dc,dn,jc,jn = K.classify(p.get("name",""), p.get("category",""))
    price=p.get("price",0); usd=p.get("price_usd",0)
    cards.append({"n":p["name"],"b":p.get("brand",""),"s":p.get("brand_slug",""),"id":p["id"],
                  "d":dc,"dn":dn,"j":jc,"jn":jn,
                  "p":price,"usd":usd,
                  "t":p["images"].get("thumb","")})
# 정렬: 대분류 순 → 중분류 코드 → 브랜드 → 가격 desc
dorder={c:i for i,c in enumerate(K.DAE_ORDER)}
cards.sort(key=lambda c:(dorder.get(c["d"],99), c["b"], c["j"], -(c["p"] or c["usd"] or 0)))

from collections import Counter
brands=sorted({c["b"] for c in cards})
dc=Counter(c["d"] for c in cards)
print(f"제품 {len(cards)} / 브랜드 {len(brands)} / 대분류 {len(dc)}")
print("대분류별:", {f'{k} {K.DAE[k]}':dc[k] for k in K.DAE_ORDER if k in dc})

# 브랜드 대표이미지
brand_img={}
for c in cards:
    if c["b"] not in brand_img and c["t"]: brand_img[c["b"]]=c["t"]

DATAJS=json.dumps(cards,ensure_ascii=False,separators=(",",":"))
BRANDIMG=json.dumps(brand_img,ensure_ascii=False)
DAEORDER=json.dumps(K.DAE_ORDER)
DAENAME=json.dumps(K.DAE,ensure_ascii=False)

HTML="""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/><title>나다운 스페이스 — 제품 카탈로그</title>
<meta name="description" content="촬영장비 제품 카탈로그 — 브랜드·카테고리별 렌탈/구매. (주)레인보우베네 나다운 스페이스."/>
<link rel="icon" href="brand/favicon.ico"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css"/>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--ink:#141414;--soft:#6b6b6b;--line:#e7e5e0;--gold:#b78a47;--navy:#1b2a4a;--cream:#f6f4f0;--ease:cubic-bezier(.16,1,.3,1)}
body{font-family:Pretendard,system-ui,sans-serif;color:var(--ink);background:#fff;-webkit-font-smoothing:antialiased}
.wrap{max-width:1400px;margin:0 auto;padding:0 clamp(14px,3.5vw,44px)}
header{border-bottom:1px solid var(--line);position:sticky;top:0;background:rgba(255,255,255,.94);backdrop-filter:blur(12px);z-index:30}
.nav{display:flex;align-items:center;justify-content:space-between;height:62px}.nav img{height:19px}
.nav a.home{font-size:13px;color:var(--soft)}
/* 브랜드 바 */
.brandbar{border-bottom:1px solid var(--line);background:var(--cream)}
.brandbar .in{padding:16px 0 14px}
.bhead{display:flex;align-items:center;gap:12px;margin-bottom:12px}
.bhead b{font-size:13px;letter-spacing:.02em}
.bsearch{margin-left:auto;border:1px solid var(--line);border-radius:999px;padding:7px 14px;font-size:13px;font-family:inherit;background:#fff;width:min(260px,46vw)}
.brands{display:flex;flex-wrap:wrap;gap:8px;max-height:150px;overflow:auto}
.brands button{display:flex;align-items:center;gap:9px;border:1px solid var(--line);background:#fff;border-radius:12px;padding:5px 14px 5px 5px;cursor:pointer;transition:.3s var(--ease);font-family:inherit}
.brands button:hover{border-color:var(--navy)}
.brands button.on{background:var(--navy);border-color:var(--navy)}
.brands button.on .bn,.brands button.on .c{color:#fff}
.brands .bi{width:34px;height:34px;border-radius:8px;background:#fff;border:1px solid var(--line);overflow:hidden;display:flex;align-items:center;justify-content:center;flex:0 0 auto}
.brands .bi img{width:100%;height:100%;object-fit:contain;mix-blend-mode:multiply}
.brands .bi.all{font-size:9px;font-weight:800;color:var(--soft)}
.brands .bn{font-size:13px;font-weight:600;white-space:nowrap;color:var(--ink)}
.brands .c{opacity:.5;font-weight:500;margin-left:4px;font-size:11px}
/* 대분류 탭 (primary) */
.daebar{position:sticky;top:62px;background:#fff;z-index:25;border-bottom:1px solid var(--line);padding:11px 0 10px}
.daes{display:flex;flex-wrap:wrap;gap:7px}
.daes button{border:1px solid var(--line);background:#fff;border-radius:9px;padding:8px 15px;font-size:14px;font-weight:700;letter-spacing:-.01em;cursor:pointer;transition:.3s var(--ease);font-family:inherit}
.daes button:hover{border-color:var(--navy)}
.daes button.on{background:var(--navy);color:#fff;border-color:var(--navy)}
.daes button .c{opacity:.55;font-weight:600;margin-left:5px;font-size:12px}
.daes button.on .c{opacity:.8}
/* 중분류 칩 (secondary) */
.jungbar{background:var(--cream);border-bottom:1px solid var(--line);overflow:hidden;transition:max-height .45s var(--ease)}
.jungbar .in{padding:11px 0}
.jungs{display:flex;flex-wrap:wrap;gap:6px}
.jungs button{border:1px solid var(--line);background:#fff;border-radius:999px;padding:6px 13px;font-size:12.5px;font-weight:600;cursor:pointer;transition:.3s var(--ease);font-family:inherit}
.jungs button:hover{border-color:var(--gold)}
.jungs button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.jungs button .c{opacity:.5;margin-left:4px}
.count{padding:16px 0 10px;font-size:13px;color:var(--soft)}
.count b{color:var(--ink);font-weight:700}
.grid{padding-bottom:20px}
.gridflow{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:20px 16px}
.ghead{grid-column:1/-1;font-size:16px;font-weight:800;letter-spacing:-.02em;margin:20px 0 4px;padding-bottom:9px;border-bottom:2px solid var(--ink);display:flex;align-items:baseline;gap:9px}
.ghead:first-child{margin-top:2px}
.ghead .gc{font-size:12.5px;font-weight:600;color:var(--soft)}
.card{border:1px solid var(--line);border-radius:13px;overflow:hidden;text-decoration:none;color:inherit;display:flex;flex-direction:column;transition:.4s var(--ease);background:#fff}
.card:hover{transform:translateY(-4px);box-shadow:0 14px 32px rgba(20,20,20,.09)}
.card .ph{aspect-ratio:1;background:var(--cream);overflow:hidden;display:flex;align-items:center;justify-content:center}
.card .ph img{width:100%;height:100%;object-fit:contain;mix-blend-mode:multiply}
.card .ph .no{color:#c9c6bf;font-size:12px}
.card .b{padding:12px 13px 15px}
.card .bt{font-size:10.5px;font-weight:700;letter-spacing:.03em;color:var(--gold);text-transform:uppercase;display:flex;justify-content:space-between;gap:6px}
.card .bt .it{color:var(--soft);font-weight:600;text-transform:none;text-align:right}
.card .nm{font-size:13px;font-weight:500;line-height:1.4;margin:6px 0 9px;height:2.8em;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.card .pr{font-size:15.5px;font-weight:800;letter-spacing:-.02em}
.card .pr small{font-size:12px;font-weight:500;color:var(--soft)}
.more{display:block;margin:14px auto 70px;border:1px solid var(--ink);background:#fff;border-radius:999px;padding:13px 34px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}
.empty{padding:60px 0 90px;text-align:center;color:var(--soft);font-size:14px}
</style></head><body>
<header><div class="wrap nav"><img src="brand/logo-black.png" alt="nadaun"/><a class="home" href="index.html">← 홈</a></div></header>
<div class="brandbar"><div class="wrap in">
  <div class="bhead"><b>브랜드</b><input class="bsearch" id="bsearch" placeholder="브랜드 검색…"/></div>
  <div class="brands" id="brands"></div>
</div></div>
<div class="daebar"><div class="wrap daes" id="daes"></div></div>
<div class="jungbar" id="jungbar"><div class="wrap in"><div class="jungs" id="jungs"></div></div></div>
<div class="wrap">
  <div class="count" id="count"></div>
  <div class="grid gridflow" id="grid"></div>
  <button class="more" id="more" style="display:none">더 보기</button>
</div>
<script>
const DATA=__DATA__, BIMG=__BRANDIMG__, DAEORDER=__DAEORDER__, DAENAME=__DAENAME__, PAGE=60;
const brands=[...new Set(DATA.map(d=>d.b))].sort();
const $=id=>document.getElementById(id);
let curB='전체',curD='전체',curJ='전체',shown=PAGE;
const fmt=d=>d.p>0?d.p.toLocaleString('ko-KR')+'원':(d.usd>0?'$'+d.usd+' <small>(원화예정)</small>':'가격문의');
const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
// 브랜드 필터만 적용된 풀 (대/중 카운트 계산용)
function byBrand(){return curB==='전체'?DATA:DATA.filter(d=>d.b===curB)}
function filtered(){return byBrand().filter(d=>(curD==='전체'||d.d===curD)&&(curJ==='전체'||d.j===curJ))}

function renderBrands(){
  const bcnt={};DATA.forEach(d=>bcnt[d.b]=(bcnt[d.b]||0)+1);
  $('brands').innerHTML=`<button data-b="전체" class="${curB==='전체'?'on':''}"><span class="bi all">ALL</span><span class="bn">전체</span><span class="c">${DATA.length}</span></button>`+
    brands.map(b=>`<button data-b="${esc(b)}" class="${curB===b?'on':''}"><span class="bi">${BIMG[b]?`<img src="${BIMG[b]}" loading="lazy">`:''}</span><span class="bn">${esc(b)}</span><span class="c">${bcnt[b]}</span></button>`).join('');
  $('brands').querySelectorAll('button').forEach(x=>x.onclick=()=>{curB=x.dataset.b;curD='전체';curJ='전체';shown=PAGE;render()});
}
function renderDaes(){
  const pool=byBrand();const dcnt={};pool.forEach(d=>dcnt[d.d]=(dcnt[d.d]||0)+1);
  const order=DAEORDER.filter(c=>dcnt[c]);
  $('daes').innerHTML=`<button data-d="전체" class="${curD==='전체'?'on':''}">전체<span class="c">${pool.length}</span></button>`+
    order.map(c=>`<button data-d="${c}" class="${curD===c?'on':''}">${DAENAME[c]}<span class="c">${dcnt[c]}</span></button>`).join('');
  $('daes').querySelectorAll('button').forEach(x=>x.onclick=()=>{curD=x.dataset.d;curJ='전체';shown=PAGE;render()});
}
function renderJungs(){
  const bar=$('jungbar');
  if(curD==='전체'){bar.style.maxHeight='0';$('jungs').innerHTML='';return}
  const pool=byBrand().filter(d=>d.d===curD);
  const jcnt={},jn={};pool.forEach(d=>{jcnt[d.j]=(jcnt[d.j]||0)+1;jn[d.j]=d.jn});
  const order=Object.keys(jcnt).sort((a,b)=>jcnt[b]-jcnt[a]);
  $('jungs').innerHTML=`<button data-j="전체" class="${curJ==='전체'?'on':''}">전체<span class="c">${pool.length}</span></button>`+
    order.map(j=>`<button data-j="${j}" class="${curJ===j?'on':''}">${esc(jn[j])}<span class="c">${jcnt[j]}</span></button>`).join('');
  bar.style.maxHeight='240px';
  $('jungs').querySelectorAll('button').forEach(x=>x.onclick=()=>{curJ=x.dataset.j;shown=PAGE;render()});
}
function card(d){const bt=curD==='전체'?`<span>${esc(d.b)}</span><span class="it">${esc(d.jn)}</span>`:`<span>${esc(d.jn)}</span>`;
  return `<a class="card" href="/product/${d.s}/${d.id}.html">
  <div class="ph">${d.t?`<img src="${d.t}" loading="lazy" alt="">`:'<span class="no">이미지 준비중</span>'}</div>
  <div class="b"><div class="bt">${bt}</div>
  <div class="nm">${esc(d.n)}</div><div class="pr">${fmt(d)}</div></div></a>`}
function render(){
  renderBrands();renderDaes();renderJungs();
  const list=filtered();
  const label=(curB!=='전체'?` · ${esc(curB)}`:'')+(curD!=='전체'?` · ${DAENAME[curD]}`:'')+(curJ!=='전체'&&list[0]?` · ${esc(list[0].jn)}`:'');
  $('count').innerHTML=`<b>${list.length.toLocaleString()}</b>개 제품${label}`;
  // 그룹 헤더: 전체=대분류별 / 카테고리 선택 시=브랜드별(소니·캐논·니콘…)
  const gkey = curD==='전체' ? 'd' : 'b';
  const gcnt={};if(gkey)list.forEach(d=>gcnt[d[gkey]]=(gcnt[d[gkey]]||0)+1);
  let html='',last=null;
  list.slice(0,shown).forEach(d=>{
    if(gkey && d[gkey]!==last){last=d[gkey];
      const lb=gkey==='d'?DAENAME[d.d]:d.b;
      html+=`<div class="ghead">${esc(lb)} <span class="gc">${gcnt[d[gkey]]}</span></div>`}
    html+=card(d);
  });
  $('grid').innerHTML=html||'<div class="empty">해당 조건의 제품이 없습니다.</div>';
  $('more').style.display=list.length>shown?'block':'none';
}
$('more').onclick=()=>{shown+=PAGE;render()};
$('bsearch').oninput=e=>{const q=e.target.value.trim().toLowerCase();
  document.querySelectorAll('#brands button').forEach(b=>{const t=b.dataset.b;b.style.display=(t==='전체'||t.toLowerCase().includes(q))?'':'none'})};
render();
</script></body></html>"""
out=(HTML.replace("__DATA__",DATAJS).replace("__BRANDIMG__",BRANDIMG)
         .replace("__DAEORDER__",DAEORDER).replace("__DAENAME__",DAENAME))
(ROOT/"catalog_category.html").write_text(out,encoding="utf-8")
print("→ catalog_category.html 생성", f"({len(out)//1024}KB)")
