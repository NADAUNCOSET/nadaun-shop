"""브랜드 내 소스 간 중복 판정 — 대표 확인용 목록 생성 (반영은 하지 않음)

    python dedupe_check.py smallrig kpp clmedia

판정 근거 (추측 금지, 근거를 화면에 같이 띄운다):
  1) 품번 일치 — SmallRig류는 제품명 끝/중간에 공식 품번(숫자 3~5자리 + 선택 알파벳)이 있다.
     품번이 양쪽 다 있고 같으면 '확실 중복'.
  2) 이름 정규화 유사도 — 품번이 없거나 다를 때 토큰 자카드 유사도로 '의심'만 표시.
산출물: _review/dedupe__<slug>.html  (확실중복 / 의심 / 고유 3탭)
"""
import os, io, json, re, sys, html

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(os.path.join(HERE, "..", "data", "products"))
OUT = os.path.join(HERE, "_review")
os.makedirs(OUT, exist_ok=True)

STOP = {"스몰리그", "smallrig", "용", "kit", "키트", "세트", "for"}


def codes(name):
    """제품명에서 품번 후보 추출 (3~5자리 숫자 + 선택 알파벳 1)."""
    return set(m.group(0).upper() for m in re.finditer(r"\b(\d{3,5}[A-Za-z]?)\b", name or ""))


def toks(name):
    t = re.split(r"[^0-9A-Za-z가-힣]+", (name or "").lower())
    return {x for x in t if x and x not in STOP and len(x) > 1}


def jac(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def run(slug, base_src, other_src):
    d = json.load(io.open(os.path.join(DATA, f"{slug}.json"), encoding="utf-8"))
    prods = list((d.get("products") or {}).values())
    base = [p for p in prods if (p.get("source") or "") == base_src]
    other = [p for p in prods if (p.get("source") or "") == other_src]
    print(f"[{slug}] {base_src} {len(base)}개 / {other_src} {len(other)}개")

    base_code = {}
    for p in base:
        for c in codes(p.get("name")):
            base_code.setdefault(c, []).append(p)
    base_tok = [(p, toks(p.get("name"))) for p in base]

    dup, susp, uniq = [], [], []
    for p in other:
        pc = codes(p.get("name"))
        hit = None
        for c in pc:
            if c in base_code:
                hit = (c, base_code[c][0])
                break
        if hit:
            dup.append({"o": p, "m": hit[1], "why": f"품번 {hit[0]} 일치"})
            continue
        pt = toks(p.get("name"))
        best, bs = None, 0.0
        for q, qt in base_tok:
            s = jac(pt, qt)
            if s > bs:
                bs, best = s, q
        if bs >= 0.62:
            susp.append({"o": p, "m": best, "why": f"이름 유사 {bs:.0%}"})
        else:
            uniq.append({"o": p, "m": best if bs >= 0.4 else None, "why": f"최대 유사 {bs:.0%}"})

    print(f"  확실중복 {len(dup)} / 의심 {len(susp)} / 고유 {len(uniq)}")

    payload = {"slug": slug, "base": base_src, "other": other_src,
               "dup": [row(x) for x in dup], "susp": [row(x) for x in susp], "uniq": [row(x) for x in uniq]}
    p = os.path.join(OUT, f"dedupe__{slug}.html")
    io.open(p, "w", encoding="utf-8").write(
        TPL.replace("__DATA__", json.dumps(payload, ensure_ascii=False)).replace("__SLUG__", slug))
    print(f"  → {p}")
    return payload


def img(p):
    return ((p.get("images") or {}).get("thumb")) or ""


def row(x):
    o, m = x["o"], x.get("m")
    return {"why": x["why"],
            "o": {"name": o.get("name"), "price": o.get("price"), "img": img(o),
                  "url": o.get("source_url"), "cat": (o.get("cat_path") or [""])[0]},
            "m": ({"name": m.get("name"), "price": m.get("price"), "img": img(m),
                   "url": m.get("source_url"), "cat": (m.get("cat_path") or [""])[0]} if m else None)}


TPL = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>중복 확인 · __SLUG__</title>
<style>
 :root{--ink:#1F1D1A;--gold:#B8862D;--line:#e6e3dd;--bad:#c0392b;--ok:#2b7a4b;--bg:#faf9f7}
 *{box-sizing:border-box}
 body{margin:0;font-family:"Pretendard","맑은 고딕",system-ui,sans-serif;color:var(--ink);background:var(--bg)}
 header{position:sticky;top:0;z-index:10;background:#fff;border-bottom:1px solid var(--line);padding:13px 20px}
 h1{margin:0 0 8px;font-size:17px;letter-spacing:-.02em}
 h1 small{font-weight:400;color:#8a847c;font-size:13px;margin-left:8px}
 .bar{display:flex;gap:7px;flex-wrap:wrap}
 button{font:inherit;padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:pointer}
 button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
 main{padding:16px 20px 70px}
 .note{font-size:13px;color:#6b6660;margin:0 0 12px;line-height:1.6}
 .pair{display:grid;grid-template-columns:1fr 1fr;gap:12px;background:#fff;border:1px solid var(--line);
       border-radius:8px;padding:11px;margin-bottom:11px;align-items:center}
 .side{display:flex;gap:10px;align-items:center;min-width:0}
 .side .t{width:74px;height:74px;flex:none;background:#f4f2ee;border-radius:5px;overflow:hidden;display:flex;align-items:center;justify-content:center}
 .side .t img{width:100%;height:100%;object-fit:contain}
 .side .x{min-width:0}
 .nm{font-size:12.5px;line-height:1.35}
 .pr{font-size:12.5px;font-weight:600;margin-top:3px}
 .cat{font-size:11px;color:#8a847c}
 .tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:4px;background:#f0ede8;color:#6b6660;margin-bottom:4px}
 .lbl{font-size:11px;color:#8a847c;margin-bottom:3px}
 a{color:var(--gold);text-decoration:none;font-size:11px}
 .none{color:#b8b2a8;font-size:12px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
 .card{background:#fff;border:1px solid var(--line);border-radius:8px;overflow:hidden}
 .card .t{aspect-ratio:1;background:#f4f2ee;display:flex;align-items:center;justify-content:center;overflow:hidden}
 .card .t img{width:100%;height:100%;object-fit:contain}
 .card .i{padding:8px 10px}
</style></head><body>
<header>
 <h1>__SLUG__ 중복 확인 <small>씨엘미디어 제품이 KPP와 겹치는지</small></h1>
 <div class="bar">
  <button class="on" data-t="dup">확실 중복 <b id="c1"></b></button>
  <button data-t="susp">의심 <b id="c2"></b></button>
  <button data-t="uniq">고유(올릴 것) <b id="c3"></b></button>
 </div>
</header>
<main id="app"></main>
<script>
const D=__DATA__; let tab='dup';
document.getElementById('c1').textContent=D.dup.length;
document.getElementById('c2').textContent=D.susp.length;
document.getElementById('c3').textContent=D.uniq.length;
document.querySelectorAll('.bar button').forEach(b=>b.onclick=()=>{
 document.querySelectorAll('.bar button').forEach(x=>x.classList.remove('on'));
 b.classList.add('on'); tab=b.dataset.t; render();});
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function won(n){return n?Number(n).toLocaleString()+'원':'<span style="color:#c0392b">가격없음</span>';}
function side(p,label){
 if(!p) return `<div class="side"><div class="x"><div class="lbl">${label}</div><div class="none">해당 없음</div></div></div>`;
 return `<div class="side"><div class="t">${p.img?`<img loading="lazy" src="${esc(p.img)}">`:''}</div>
  <div class="x"><div class="lbl">${label}</div><div class="nm">${esc(p.name)}</div>
   <div class="pr">${won(p.price)}</div><div class="cat">${esc(p.cat)}</div>
   <a href="${esc(p.url)}" target="_blank" rel="noopener">원본 ↗</a></div></div>`;
}
function render(){
 const app=document.getElementById('app');
 if(tab==='uniq'){
  app.innerHTML=`<p class="note">KPP에 없는 <b>씨엘미디어 단독 제품 ${D.uniq.length}개</b> — 이것만 우리 사이트에 올리면 됩니다.</p>`+
   '<div class="grid">'+D.uniq.map(r=>`<div class="card"><div class="t">${r.o.img?`<img loading="lazy" src="${esc(r.o.img)}">`:''}</div>
     <div class="i"><div class="nm">${esc(r.o.name)}</div><div class="pr">${won(r.o.price)}</div>
     <div class="cat">${esc(r.o.cat)}</div><a href="${esc(r.o.url)}" target="_blank">원본 ↗</a></div></div>`).join('')+'</div>';
  return;
 }
 const list = tab==='dup'?D.dup:D.susp;
 const head = tab==='dup'
  ? `<p class="note">품번이 같아 <b>같은 제품으로 판정</b>된 ${D.dup.length}건 — 씨엘 쪽을 빼면 됩니다.</p>`
  : `<p class="note">이름이 비슷해 <b>중복 의심</b>인 ${D.susp.length}건 — 눈으로 확인이 필요합니다.</p>`;
 app.innerHTML = head + (list.length? list.map(r=>`<div class="pair">
   ${side(r.o,'씨엘미디어')}${side(r.m,'KPP')}
   <div style="grid-column:1/-1"><span class="tag">${esc(r.why)}</span></div></div>`).join('')
   : '<div class="none" style="padding:40px 0;text-align:center">해당 없음</div>');
}
render();
</script></body></html>
"""


if __name__ == "__main__":
    slug = sys.argv[1] if len(sys.argv) > 1 else "smallrig"
    base = sys.argv[2] if len(sys.argv) > 2 else "kpp"
    other = sys.argv[3] if len(sys.argv) > 3 else "clmedia"
    run(slug, base, other)
