"""pending JSON → 데이터가 박힌 검수 HTML 생성 (열면 바로 보임, 파일 선택 불필요)

    python make_review.py                 # _pending 전부 생성
    python make_review.py kpp__SMALLRIG   # 하나만

산출물: _review/<name>.html
"""
import os, io, json, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(os.path.join(HERE, "..", "data"))
PENDING = os.path.join(DATA, "_pending")
OUTDIR = os.path.join(HERE, "_review")
os.makedirs(OUTDIR, exist_ok=True)

TPL = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>검수 · __BRAND__</title>
<style>
 :root{--ink:#1F1D1A;--gold:#B8862D;--line:#e6e3dd;--bad:#c0392b;--ok:#2b7a4b;--bg:#faf9f7}
 *{box-sizing:border-box}
 body{margin:0;font-family:"Pretendard","맑은 고딕",system-ui,sans-serif;color:var(--ink);background:var(--bg)}
 header{position:sticky;top:0;z-index:10;background:#fff;border-bottom:1px solid var(--line);padding:13px 20px}
 h1{margin:0 0 7px;font-size:17px;letter-spacing:-.02em}
 h1 small{font-weight:400;color:#8a847c;font-size:13px;margin-left:8px}
 .meta{font-size:13px;color:#6b6660;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
 .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;background:#f0ede8}
 .pill.bad{background:#fde8e6;color:var(--bad)} .pill.ok{background:#e6f4ec;color:var(--ok)}
 .bar{display:flex;gap:7px;margin-top:10px;flex-wrap:wrap;align-items:center}
 button{font:inherit;padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:pointer}
 button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
 a.srcbtn{font:inherit;padding:6px 12px;border:1px solid var(--gold);border-radius:6px;color:var(--gold);text-decoration:none}
 main{padding:18px 20px 80px}
 .cat{margin-bottom:26px}
 .cat h2{font-size:14px;margin:0;padding-bottom:6px;border-bottom:1px solid var(--line);
         display:flex;justify-content:space-between;align-items:baseline}
 .cat h2 span{font-size:12px;color:#8a847c;font-weight:400}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(185px,1fr));gap:13px;margin-top:12px}
 .card{background:#fff;border:1px solid var(--line);border-radius:8px;overflow:hidden;display:flex;flex-direction:column}
 .card.flag{border-color:var(--bad)}
 .thumb{aspect-ratio:1;background:#f4f2ee;display:flex;align-items:center;justify-content:center;overflow:hidden}
 .thumb img{width:100%;height:100%;object-fit:contain}
 .thumb.none{color:var(--bad);font-size:12px}
 .info{padding:9px 10px;display:flex;flex-direction:column;gap:5px;flex:1}
 .nm{font-size:12.5px;line-height:1.35;max-height:3.5em;overflow:hidden}
 .pr{font-size:13px;font-weight:600} .pr.zero{color:var(--bad)}
 .tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:auto}
 .tag{font-size:10.5px;padding:1px 6px;border-radius:4px;background:#f0ede8;color:#6b6660}
 .tag.bad{background:#fde8e6;color:var(--bad)}
 a.src{font-size:11px;color:var(--gold);text-decoration:none}
 .empty{padding:60px 0;text-align:center;color:#8a847c}
</style></head><body>
<header>
 <h1>__BRAND__ <small>__SITE__ 미러링 검수</small></h1>
 <div class="meta" id="meta"></div>
 <div class="bar">
   <button class="on" data-f="all">전체</button>
   <button data-f="flag">문제만</button>
   <button data-f="noprice">가격없음</button>
   <button data-f="nodetail">상세없음</button>
   <button data-f="noimg">이미지없음</button>
   <a class="srcbtn" id="srcLink" target="_blank" rel="noopener">원본 브랜드몰 ↗</a>
 </div>
</header>
<main id="app"></main>
<script>
const DATA = __DATA__;
let mode = 'all';
document.querySelectorAll('.bar button').forEach(b => b.onclick = () => {
  document.querySelectorAll('.bar button').forEach(x => x.classList.remove('on'));
  b.classList.add('on'); mode = b.dataset.f; render();
});
function flags(p){const f=[];
  if(!p.price) f.push('가격0');
  if(!(p.images_src&&p.images_src.main&&p.images_src.main.length)) f.push('대표이미지X');
  if(!(p.images_src&&p.images_src.detail&&p.images_src.detail.length)) f.push('상세X');
  return f;}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function render(){
 const prods=Object.values(DATA.products||{}), st=DATA.stats||{};
 document.getElementById('meta').innerHTML =
  `<span>제품 <b>${prods.length}</b>개</span><span>카테고리 <b>${Object.keys(DATA.categories||{}).length}</b>개</span>`+
  `<span class="pill ${st.no_price?'bad':'ok'}">가격없음 ${st.no_price??0}</span>`+
  `<span class="pill ${st.no_main_image?'bad':'ok'}">대표이미지없음 ${st.no_main_image??0}</span>`+
  `<span class="pill ${st.no_detail?'bad':'ok'}">상세없음 ${st.no_detail??0}</span>`;
 document.getElementById('srcLink').href = DATA.brand_url||'#';
 const keep=p=>{const f=flags(p);
   if(mode==='all')return true; if(mode==='flag')return f.length>0;
   if(mode==='noprice')return !p.price;
   if(mode==='nodetail')return f.includes('상세X');
   if(mode==='noimg')return f.includes('대표이미지X'); return true;};
 const byCat={};
 prods.filter(keep).forEach(p=>{const c=(p.cat_path&&p.cat_path[0])||'(분류없음)';(byCat[c]=byCat[c]||[]).push(p);});
 const cats=Object.keys(byCat).sort();
 const app=document.getElementById('app');
 if(!cats.length){app.innerHTML='<div class="empty">해당 조건의 제품이 없습니다.</div>';return;}
 app.innerHTML=cats.map(c=>`<section class="cat"><h2>${esc(c)} <span>${byCat[c].length}개</span></h2>
   <div class="grid">${byCat[c].map(card).join('')}</div></section>`).join('');
}
function card(p){
 const f=flags(p);
 const img=(p.images_src&&p.images_src.main&&p.images_src.main[0])||'';
 const price=p.price?p.price.toLocaleString()+'원':(p.inquiry?'전화문의':'가격없음');
 return `<div class="card ${f.length?'flag':''}">
  <div class="thumb ${img?'':'none'}">${img?`<img loading="lazy" src="${esc(img)}" alt="">`:'이미지 없음'}</div>
  <div class="info"><div class="nm">${esc(p.name)}</div>
   <div class="pr ${p.price?'':'zero'}">${price}</div>
   <div class="tags">${f.map(x=>`<span class="tag bad">${x}</span>`).join('')}
    ${p.images_src&&p.images_src.detail?`<span class="tag">상세 ${p.images_src.detail.length}</span>`:''}</div>
   <a class="src" href="${esc(p.source_url)}" target="_blank" rel="noopener">원본 ↗</a></div></div>`;
}
render();
</script></body></html>
"""


def build(path):
    name = os.path.splitext(os.path.basename(path))[0]
    d = json.load(io.open(path, encoding="utf-8"))
    html = (TPL
            .replace("__DATA__", json.dumps(d, ensure_ascii=False))
            .replace("__BRAND__", d.get("brand", name))
            .replace("__SITE__", d.get("site", "")))
    out = os.path.join(OUTDIR, name + ".html")
    io.open(out, "w", encoding="utf-8").write(html)
    return out, d.get("product_count") or len(d.get("products") or {})


if __name__ == "__main__":
    targets = sys.argv[1:]
    files = ([os.path.join(PENDING, t if t.endswith(".json") else t + ".json") for t in targets]
             if targets else sorted(glob.glob(os.path.join(PENDING, "*.json"))))
    if not files:
        print("_pending 에 JSON이 없습니다."); sys.exit(1)
    for f in files:
        if not os.path.exists(f):
            print("없음:", f); continue
        out, n = build(f)
        print(f"생성: {out}  (제품 {n}개)")
