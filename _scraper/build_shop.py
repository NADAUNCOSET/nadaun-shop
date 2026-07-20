# -*- coding: utf-8 -*-
"""[통합 카탈로그] data/products/*.json → catalog.html(브랜드별) + catalog_category.html(제품별).
   ★2026-07-20 대표 지시 IA: 상단 12 고정 대분류(구매Shop). 각 대분류 안에
     - 브랜드별 = 브랜드 타일 쫙 → 클릭 시 그 브랜드 세부(중분류)
     - 제품별   = 브랜드별로 나뉜 제품
   두 페이지는 동일 템플릿, 초기 MODE만 다름(헤더 토글로 클라이언트 전환).
   브랜드→대분류 매핑=top12.BRAND_CAT(브랜드 우선), 미분류통(_misc)=키워드분류.
"""
import sys, io, json
from pathlib import Path
from collections import Counter, defaultdict
sys.path.insert(0, str(Path(__file__).parent))
import kpp_classify as K
import source_rules as SR
import top12 as T
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(r"\\Nadaunproject\nadaunproject\_Site\nadaun-shop")
DATA = ROOT/"data"/"products"
SRC_IDX = SR.build_index(DATA)

# ── 제품 로드 + 12분류 + 세부(중분류) ──
cards = []
disp_vote = defaultdict(Counter)   # slug → 표시명 후보
for f in sorted(DATA.glob("*.json")):
    if f.stem == "_index": continue
    d = json.load(open(f, encoding="utf-8"))
    top_slug = d.get("brand_slug") or f.stem
    for p in d.get("products", {}).values():
        slug = p.get("brand_slug") or top_slug
        if not SR.allowed(p, slug, SRC_IDX): continue
        nm, cat = p.get("name",""), p.get("category","")
        if p.get("source") == "kpp" and p.get("ca_id"):
            dc,dn,jc,jn = K.from_ca_id(p["ca_id"], nm, cat)
        else:
            dc,dn,jc,jn = K.classify(nm, cat)
        tcode, tname = T.resolve(slug, dc, jc, nm)
        disp = p.get("brand") or slug
        disp_vote[slug][disp] += 1
        cards.append({"n":nm, "s":slug, "id":p["id"], "c":tcode, "sub":jn,
                      "p":p.get("price",0), "usd":p.get("price_usd",0),
                      "t":p.get("images",{}).get("thumb","")})

# 슬러그별 대표 표시명 + 대표 이미지
BDISP = {s: v.most_common(1)[0][0] for s, v in disp_vote.items()}
for s in T.PSEUDO:                    # 미분류통 = 깔끔히 "기타"
    if s in BDISP: BDISP[s] = "기타"
BIMG = {}
for c in cards:
    if c["s"] not in BIMG and c["t"]:
        BIMG[c["s"]] = c["t"]
for c in cards:                      # 카드에 표시명 부여
    c["b"] = BDISP.get(c["s"], c["s"])

# 미분류통(_misc/_custom)은 브랜드별 타일에서 제외 → 실브랜드만
REAL = {s for s in BDISP if s not in T.PSEUDO}

# ── 통계 ──
tc = Counter(c["c"] for c in cards)
brands_in = defaultdict(set)
for c in cards:
    if c["s"] in REAL: brands_in[c["c"]].add(c["s"])
print(f"제품 {len(cards)} / 실브랜드 {len(REAL)}")
print("대분류별:", {T.TOP[t]: f"{tc[t]}개/{len(brands_in[t])}br" for t in T.TOPORDER if tc[t]})

# ── 정렬: 대분류 순 → 실브랜드먼저(기타 뒤로) → 브랜드 → 세부 → 가격desc ──
torder = {c:i for i,c in enumerate(T.TOPORDER)}
cards.sort(key=lambda c:(torder.get(c["c"],99), c["s"] in T.PSEUDO, c["b"], c["sub"], -(c["p"] or c["usd"] or 0)))

DATAJS  = json.dumps([{k:c[k] for k in ("n","b","s","id","c","sub","p","usd","t")} for c in cards],
                     ensure_ascii=False, separators=(",",":"))
BIMGJS  = json.dumps(BIMG, ensure_ascii=False, separators=(",",":"))
TOPJS   = json.dumps(T.TOP, ensure_ascii=False)
TOPORDJS= json.dumps(T.TOPORDER)
REALJS  = json.dumps(sorted(REAL), ensure_ascii=False)

TEMPLATE = r"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/><title>__TITLE__</title>
<meta name="description" content="촬영장비 제품 카탈로그 — 12개 대분류·브랜드별 구매. (주)레인보우베네 나다운 스페이스."/>
<link rel="icon" href="brand/favicon.ico"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css"/>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--ink:#141414;--soft:#6b6b6b;--line:#e7e5e0;--gold:#b78a47;--navy:#1b2a4a;--cream:#f6f4f0;--ease:cubic-bezier(.16,1,.3,1)}
body{font-family:Pretendard,system-ui,sans-serif;color:var(--ink);background:#fff;-webkit-font-smoothing:antialiased}
.wrap{max-width:1400px;margin:0 auto;padding:0 clamp(14px,3.5vw,44px)}
header{border-bottom:1px solid var(--line);position:sticky;top:0;background:rgba(255,255,255,.95);backdrop-filter:blur(12px);z-index:40}
.nav{display:flex;align-items:center;gap:16px;height:62px}.nav .logo{height:20px}
.nav .home{font-size:13px;color:var(--soft);text-decoration:none}
.toggle{margin-left:auto;display:flex;gap:6px;background:var(--cream);border:1px solid var(--line);border-radius:999px;padding:4px}
.toggle a{font-size:13px;font-weight:700;padding:7px 18px;border-radius:999px;text-decoration:none;color:var(--soft);transition:.3s var(--ease)}
.toggle a.on{background:var(--navy);color:#fff}
.toggle a.on.b{background:var(--gold)}
/* 대분류 탭 */
.catbar{position:sticky;top:62px;background:#fff;z-index:30;border-bottom:1px solid var(--line);padding:11px 0 10px}
.cats{display:flex;flex-wrap:wrap;gap:7px}
.cats button{border:1px solid var(--line);background:#fff;border-radius:9px;padding:8px 14px;font-size:13.5px;font-weight:700;letter-spacing:-.01em;cursor:pointer;transition:.3s var(--ease);font-family:inherit}
.cats button:hover{border-color:var(--navy)}
.cats button.on{background:var(--navy);color:#fff;border-color:var(--navy)}
.cats button .c{opacity:.55;font-weight:600;margin-left:5px;font-size:11.5px}
.cats button.on .c{opacity:.85}
.cats button:disabled{opacity:.32;cursor:default}
/* 세부(중분류) 칩 — 제품별 브랜드 진입시 */
.subbar{background:var(--cream);border-bottom:1px solid var(--line);overflow:hidden;max-height:0;transition:max-height .4s var(--ease)}
.subbar.open{max-height:220px}
.subbar .in{padding:11px 0}
.subs{display:flex;flex-wrap:wrap;gap:6px}
.subs button{border:1px solid var(--line);background:#fff;border-radius:999px;padding:6px 13px;font-size:12.5px;font-weight:600;cursor:pointer;transition:.3s var(--ease);font-family:inherit}
.subs button:hover{border-color:var(--gold)}
.subs button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.subs button .c{opacity:.5;margin-left:4px}
.crumb{padding:16px 0 4px;font-size:13px;color:var(--soft);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.crumb b{color:var(--ink);font-weight:700}
.crumb .back{border:1px solid var(--line);background:#fff;border-radius:999px;padding:5px 13px;font-size:12.5px;font-weight:600;cursor:pointer;font-family:inherit;color:var(--navy)}
/* 섹션 헤더 */
.sec{margin:26px 0 2px;display:flex;align-items:baseline;gap:10px;padding-bottom:9px;border-bottom:2px solid var(--ink)}
.sec:first-child{margin-top:6px}
.sec h2{font-size:17px;font-weight:800;letter-spacing:-.02em}
.sec .c{font-size:12.5px;font-weight:600;color:var(--soft)}
.sec .more{margin-left:auto;font-size:12.5px;font-weight:700;color:var(--gold);cursor:pointer}
/* 브랜드 타일 그리드 */
.btiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px;padding:18px 0 6px}
.btile{border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#fff;cursor:pointer;transition:.4s var(--ease);display:flex;flex-direction:column;text-align:left}
.btile:hover{transform:translateY(-4px);box-shadow:0 14px 30px rgba(20,20,20,.10);border-color:var(--navy)}
.btile .im{aspect-ratio:4/3;background:var(--cream);display:flex;align-items:center;justify-content:center;overflow:hidden}
.btile .im img{width:100%;height:100%;object-fit:contain;mix-blend-mode:multiply}
.btile .im .no{color:#c9c6bf;font-size:11px}
.btile .bb{padding:11px 13px 13px}
.btile .bn{font-size:14px;font-weight:700;letter-spacing:-.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.btile .bc{font-size:11.5px;color:var(--soft);margin-top:3px}
/* 제품 카드 그리드 */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:20px 16px;padding:16px 0 20px}
.ghead{grid-column:1/-1;font-size:14.5px;font-weight:800;letter-spacing:-.02em;margin:16px 0 2px;padding-bottom:8px;border-bottom:1px solid var(--line);display:flex;align-items:baseline;gap:9px}
.ghead .gc{font-size:12px;font-weight:600;color:var(--soft)}
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
.morebtn{display:block;margin:14px auto 70px;border:1px solid var(--ink);background:#fff;border-radius:999px;padding:13px 34px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}
.empty{padding:60px 0 90px;text-align:center;color:var(--soft);font-size:14px}
</style></head><body>
<header><div class="wrap nav">
  <img class="logo" src="brand/logo-black.png" alt="nadaun"/>
  <a class="home" href="index.html">← 홈</a>
  <div class="toggle">
    <a href="catalog.html" id="tgB" class="b">브랜드별</a>
    <a href="catalog_category.html" id="tgP">제품별</a>
  </div>
</div></header>
<div class="catbar"><div class="wrap cats" id="cats"></div></div>
<div class="subbar" id="subbar"><div class="wrap in"><div class="subs" id="subs"></div></div></div>
<div class="wrap">
  <div class="crumb" id="crumb"></div>
  <div id="body"></div>
</div>
<script>
const DATA=__DATA__, BIMG=__BIMG__, TOP=__TOP__, TOPORDER=__TOPORDER__, REAL=new Set(__REAL__);
const MODE0="__MODE__", PAGE=60;
const $=id=>document.getElementById(id);
const esc=s=>(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const fmt=d=>d.p>0?d.p.toLocaleString('ko-KR')+'원':(d.usd>0?'$'+d.usd+' <small>(원화예정)</small>':'가격문의');
const bdisp={}; DATA.forEach(d=>{if(!bdisp[d.s])bdisp[d.s]=d.b});
// 대분류별 카운트
const catCnt={}; DATA.forEach(d=>catCnt[d.c]=(catCnt[d.c]||0)+1);
const catBrands={}; TOPORDER.forEach(t=>catBrands[t]=new Set());
DATA.forEach(d=>{if(REAL.has(d.s))catBrands[d.c].add(d.s)});

let mode=MODE0, curCat='all', curBrand=null, curSub='전체', shown=PAGE;

// ── 탭/토글 ──
function syncToggle(){$('tgB').className='b'+(mode==='brand'?' on':'');$('tgP').className=(mode==='product'?' on':'');}
function renderCats(){
  const showCnt=t=>mode==='brand'?catBrands[t].size:catCnt[t]||0;
  let h=`<button data-t="all" class="${curCat==='all'?'on':''}">전체<span class="c">${mode==='brand'?REAL.size:DATA.length.toLocaleString()}</span></button>`;
  h+=TOPORDER.map((t,i)=>{const n=showCnt(t);return `<button data-t="${t}" class="${curCat===t?'on':''}" ${n?'':'disabled'}>${String(i+1).padStart(2,'0')}. ${TOP[t]}<span class="c">${n}</span></button>`}).join('');
  $('cats').innerHTML=h;
  $('cats').querySelectorAll('button').forEach(b=>b.onclick=()=>{if(b.disabled)return;curCat=b.dataset.t;curBrand=null;curSub='전체';shown=PAGE;render()});
}

// ── 브랜드별 ──
function brandTiles(t){
  const slugs=[...catBrands[t]].sort((a,b)=>bdisp[a].localeCompare(bdisp[b],'ko'));
  const cnt={}; DATA.forEach(d=>{if(d.c===t&&REAL.has(d.s))cnt[d.s]=(cnt[d.s]||0)+1});
  return slugs.map(s=>`<button class="btile" data-s="${s}" data-t="${t}">
    <div class="im">${BIMG[s]?`<img src="${BIMG[s]}" loading="lazy" alt="">`:'<span class="no">이미지</span>'}</div>
    <div class="bb"><div class="bn">${esc(bdisp[s])}</div><div class="bc">${cnt[s]||0}개 제품</div></div></button>`).join('');
}
function renderBrand(){
  $('subbar').classList.remove('open');
  const cats=curCat==='all'?TOPORDER.filter(t=>catBrands[t].size):[curCat];
  $('crumb').innerHTML=curCat==='all'?`브랜드별 · <b>전체 ${REAL.size}개 브랜드</b>`:`브랜드별 · <b>${TOP[curCat]}</b> · ${catBrands[curCat].size}개 브랜드`;
  let h='';
  cats.forEach((t,i)=>{
    h+=`<div class="sec"><h2>${String(TOPORDER.indexOf(t)+1).padStart(2,'0')}. ${TOP[t]}</h2><span class="c">${catBrands[t].size}개 브랜드</span></div>`;
    h+=`<div class="btiles">${brandTiles(t)}</div>`;
  });
  $('body').innerHTML=h||'<div class="empty">브랜드가 없습니다.</div>';
  $('body').querySelectorAll('.btile').forEach(b=>b.onclick=()=>{mode='product';curCat=b.dataset.t;curBrand=b.dataset.s;curSub='전체';shown=PAGE;render()});
}

// ── 제품별 ──
function pool(){return DATA.filter(d=>(curCat==='all'||d.c===curCat)&&(!curBrand||d.s===curBrand)&&(curSub==='전체'||d.sub===curSub))}
function renderSubs(){
  const bar=$('subbar');
  if(!curBrand){bar.classList.remove('open');$('subs').innerHTML='';return}
  const p=DATA.filter(d=>d.s===curBrand&&(curCat==='all'||d.c===curCat));
  const sc={}; p.forEach(d=>sc[d.sub]=(sc[d.sub]||0)+1);
  const order=Object.keys(sc).sort((a,b)=>sc[b]-sc[a]);
  $('subs').innerHTML=`<button data-j="전체" class="${curSub==='전체'?'on':''}">전체<span class="c">${p.length}</span></button>`+
    order.map(j=>`<button data-j="${esc(j)}" class="${curSub===j?'on':''}">${esc(j)}<span class="c">${sc[j]}</span></button>`).join('');
  bar.classList.add('open');
  $('subs').querySelectorAll('button').forEach(b=>b.onclick=()=>{curSub=b.dataset.j;shown=PAGE;render()});
}
function card(d){
  return `<a class="card" href="/product/${d.s}/${d.id}.html">
  <div class="ph">${d.t?`<img src="${d.t}" loading="lazy" alt="">`:'<span class="no">이미지 준비중</span>'}</div>
  <div class="b"><div class="bt"><span>${esc(d.b)}</span><span class="it">${esc(d.sub)}</span></div>
  <div class="nm">${esc(d.n)}</div><div class="pr">${fmt(d)}</div></div></a>`;
}
function renderProduct(){
  renderSubs();
  const list=pool();
  let cr=`제품별`;
  if(curCat!=='all')cr+=` · <b>${TOP[curCat]}</b>`;
  if(curBrand)cr+=` · <b>${esc(bdisp[curBrand])}</b> <button class="back" id="bk">← 브랜드 전체</button>`;
  cr+=` · ${list.length.toLocaleString()}개`;
  $('crumb').innerHTML=cr;
  const bk=$('bk'); if(bk)bk.onclick=()=>{mode='brand';curBrand=null;curSub='전체';shown=PAGE;render()};
  // 그룹: 대분류 선택+브랜드 미선택 → 브랜드별 / 그 외 → 없음(단일)
  const groupByBrand = !curBrand;
  const gc={}; if(groupByBrand)list.forEach(d=>gc[d.s]=(gc[d.s]||0)+1);
  let h='',last=null;
  list.slice(0,shown).forEach(d=>{
    if(groupByBrand && d.s!==last){last=d.s;
      h+=`<div class="ghead">${esc(d.b)} <span class="gc">${gc[d.s]}</span></div>`}
    h+=card(d);
  });
  h=h?`<div class="grid">${h}</div>`:'<div class="empty">해당 조건의 제품이 없습니다.</div>';
  if(list.length>shown)h+=`<button class="morebtn" id="more">더 보기 (${(list.length-shown).toLocaleString()}개 남음)</button>`;
  $('body').innerHTML=h;
  const m=$('more'); if(m)m.onclick=()=>{shown+=PAGE;renderProduct()};
}

function render(){syncToggle();renderCats();(mode==='brand'?renderBrand:renderProduct)()}
// 토글 클릭=페이지 이동 대신 모드전환(같은 데이터)
$('tgB').onclick=e=>{e.preventDefault();mode='brand';curBrand=null;curSub='전체';shown=PAGE;render()};
$('tgP').onclick=e=>{e.preventDefault();mode='product';curSub='전체';shown=PAGE;render()};
render();
</script></body></html>"""

def emit(path, mode, title):
    out = (TEMPLATE.replace("__DATA__", DATAJS).replace("__BIMG__", BIMGJS)
           .replace("__TOP__", TOPJS).replace("__TOPORDER__", TOPORDJS)
           .replace("__REAL__", REALJS).replace("__MODE__", mode).replace("__TITLE__", title))
    (ROOT/path).write_text(out, encoding="utf-8")
    print(f"→ {path} ({len(out)//1024}KB, mode={mode})")

def main():
    emit("catalog.html", "brand", "나다운 스페이스 — 브랜드별 카탈로그")
    emit("catalog_category.html", "product", "나다운 스페이스 — 제품별 카탈로그")

if __name__ == "__main__":
    main()
