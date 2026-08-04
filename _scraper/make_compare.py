"""KPP 원본 미러링 ↔ 현재 shop.nadaun.co 비교 화면 생성

    python make_compare.py SMALLRIG smallrig
      (첫 인자=미러링 브랜드명, 둘째=현재 data/products 의 slug)

산출물: _review/compare__<brand>.html   (열면 바로 보임)
"""
import os, io, json, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(os.path.join(HERE, "..", "data"))
OUT = os.path.join(HERE, "_review")
os.makedirs(OUT, exist_ok=True)


def load_mirror(brand):
    p = os.path.join(DATA, "_pending", f"kpp__{brand}.json")
    return json.load(io.open(p, encoding="utf-8"))


def load_current(slug):
    p = os.path.join(DATA, "products", f"{slug}.json")
    if not os.path.exists(p):
        return None
    return json.load(io.open(p, encoding="utf-8"))


def build(brand, slug):
    mir = load_mirror(brand)
    cur = load_current(slug)
    mp = mir.get("products") or {}
    cp = (cur.get("products") or {}) if cur else {}

    mir_items = list(mp.values())
    cur_items = list(cp.values())

    # KPP source_id 기준 대조
    mir_ids = {str(v.get("source_id")): v for v in mir_items}
    cur_kpp = {str(v.get("source_id")): v for v in cur_items if (v.get("source") or "") == "kpp"}

    both = sorted(set(mir_ids) & set(cur_kpp))
    only_mir = sorted(set(mir_ids) - set(cur_kpp))
    only_cur_kpp = sorted(set(cur_kpp) - set(mir_ids))
    other_src = [v for v in cur_items if (v.get("source") or "") != "kpp"]

    # 가격 차이
    price_diff = []
    for i in both:
        a, b = mir_ids[i], cur_kpp[i]
        if int(a.get("price") or 0) != int(b.get("price") or 0):
            price_diff.append({"id": i, "name": a.get("name"), "mirror": a.get("price") or 0,
                               "current": b.get("price") or 0,
                               "url": a.get("source_url")})

    def stats(items, imgkey):
        n = len(items)
        if imgkey == "mirror":
            nop = sum(1 for x in items if not x.get("price"))
            noi = sum(1 for x in items if not ((x.get("images_src") or {}).get("main")))
            nod = sum(1 for x in items if not ((x.get("images_src") or {}).get("detail")))
        else:
            nop = sum(1 for x in items if not x.get("price"))
            noi = sum(1 for x in items if not ((x.get("images") or {}).get("thumb")))
            nod = sum(1 for x in items if not ((x.get("images") or {}).get("detail")))
        return {"total": n, "no_price": nop, "no_img": noi, "no_detail": nod}

    mcat = collections.Counter((v.get("cat_path") or ["(없음)"])[0] for v in mir_items)
    ccat = collections.Counter((v.get("cat_path") or ["(없음)"])[0] for v in cur_items)
    csrc = collections.Counter(v.get("source") or "?" for v in cur_items)

    payload = {
        "brand": brand, "slug": slug,
        "brand_url": mir.get("brand_url"),
        "mirror": {
            "stats": stats(mir_items, "mirror"),
            "cats": mcat.most_common(),
            "cat_count": len(mir.get("categories") or {}),
        },
        "current": {
            "stats": stats(cur_items, "current") if cur else {"total": 0, "no_price": 0, "no_img": 0, "no_detail": 0},
            "cats": ccat.most_common(),
            "srcs": csrc.most_common(),
        },
        "diff": {
            "both": len(both), "only_mirror": len(only_mir),
            "only_current_kpp": len(only_cur_kpp), "other_source": len(other_src),
        },
        "only_mirror_items": [
            {"name": mir_ids[i].get("name"), "price": mir_ids[i].get("price"),
             "cat": (mir_ids[i].get("cat_path") or [""])[0],
             "img": ((mir_ids[i].get("images_src") or {}).get("main") or [""])[0],
             "url": mir_ids[i].get("source_url")} for i in only_mir[:400]],
        "only_current_items": [
            {"name": cur_kpp[i].get("name"), "price": cur_kpp[i].get("price"),
             "cat": (cur_kpp[i].get("cat_path") or [""])[0],
             "img": ((cur_kpp[i].get("images") or {}).get("thumb") or ""),
             "url": cur_kpp[i].get("source_url")} for i in only_cur_kpp[:400]],
        "other_src_items": [
            {"name": v.get("name"), "price": v.get("price"), "src": v.get("source"),
             "cat": (v.get("cat_path") or [""])[0],
             "img": ((v.get("images") or {}).get("thumb") or ""),
             "url": v.get("source_url")} for v in other_src[:400]],
        "price_diff": price_diff[:300],
    }

    html = TPL.replace("__DATA__", json.dumps(payload, ensure_ascii=False)).replace("__BRAND__", brand)
    path = os.path.join(OUT, f"compare__{brand}.html")
    io.open(path, "w", encoding="utf-8").write(html)
    return path, payload


TPL = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>비교 · __BRAND__</title>
<style>
 :root{--ink:#1F1D1A;--gold:#B8862D;--line:#e6e3dd;--bad:#c0392b;--ok:#2b7a4b;--bg:#faf9f7}
 *{box-sizing:border-box}
 body{margin:0;font-family:"Pretendard","맑은 고딕",system-ui,sans-serif;color:var(--ink);background:var(--bg)}
 header{position:sticky;top:0;z-index:10;background:#fff;border-bottom:1px solid var(--line);padding:13px 20px}
 h1{margin:0 0 8px;font-size:17px;letter-spacing:-.02em}
 h1 small{font-weight:400;color:#8a847c;font-size:13px;margin-left:8px}
 .cols{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:0 0 4px}
 .col{border:1px solid var(--line);border-radius:8px;padding:10px 12px;background:#fff}
 .col h3{margin:0 0 6px;font-size:13px;letter-spacing:-.01em}
 .col.mir h3{color:var(--ok)} .col.cur h3{color:var(--gold)}
 .kv{font-size:12.5px;color:#6b6660;display:flex;gap:12px;flex-wrap:wrap}
 .kv b{color:var(--ink)}
 .bad{color:var(--bad)}
 .bar{display:flex;gap:7px;margin-top:10px;flex-wrap:wrap;align-items:center}
 button{font:inherit;padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:pointer}
 button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
 a.srcbtn{font:inherit;padding:6px 12px;border:1px solid var(--gold);border-radius:6px;color:var(--gold);text-decoration:none}
 main{padding:16px 20px 70px}
 table{border-collapse:collapse;width:100%;background:#fff;font-size:12.5px}
 th,td{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top}
 th{background:#f4f2ee;font-weight:600;position:sticky;top:0}
 td.num{text-align:right;font-variant-numeric:tabular-nums}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
 .card{background:#fff;border:1px solid var(--line);border-radius:8px;overflow:hidden;display:flex;flex-direction:column}
 .thumb{aspect-ratio:1;background:#f4f2ee;display:flex;align-items:center;justify-content:center;overflow:hidden}
 .thumb img{width:100%;height:100%;object-fit:contain}
 .thumb.none{color:var(--bad);font-size:12px}
 .info{padding:8px 10px;display:flex;flex-direction:column;gap:4px;flex:1}
 .nm{font-size:12.5px;line-height:1.35;max-height:3.5em;overflow:hidden}
 .pr{font-size:12.5px;font-weight:600}
 .cat{font-size:11px;color:#8a847c}
 a.src{font-size:11px;color:var(--gold);text-decoration:none;margin-top:auto}
 .note{font-size:12.5px;color:#6b6660;margin:0 0 12px;line-height:1.6}
 .empty{padding:50px 0;text-align:center;color:#8a847c}
</style></head><body>
<header>
 <h1>__BRAND__ <small>KPP 원본 미러링 ↔ 현재 shop.nadaun.co</small></h1>
 <div class="cols">
   <div class="col mir"><h3>① KPP 원본 미러링 (새로 수집)</h3><div class="kv" id="mstat"></div></div>
   <div class="col cur"><h3>② 현재 shop.nadaun.co</h3><div class="kv" id="cstat"></div></div>
 </div>
 <div class="bar">
   <button class="on" data-t="cat">카테고리 비교</button>
   <button data-t="onlymir">KPP에만 있음</button>
   <button data-t="onlycur">우리에만 있음(KPP출처)</button>
   <button data-t="othersrc">타 소스 제품</button>
   <button data-t="price">가격 차이</button>
   <a class="srcbtn" id="srcLink" target="_blank" rel="noopener">KPP 브랜드몰 ↗</a>
 </div>
</header>
<main id="app"></main>
<script>
const D = __DATA__;
let tab='cat';
document.querySelectorAll('.bar button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.bar button').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); tab=b.dataset.t; render();});
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function won(n){return n?Number(n).toLocaleString()+'원':'<span class="bad">없음</span>';}

const m=D.mirror.stats, c=D.current.stats;
document.getElementById('mstat').innerHTML =
 `<span>제품 <b>${m.total.toLocaleString()}</b></span><span>카테고리 <b>${D.mirror.cat_count}</b></span>`+
 `<span class="${m.no_price?'bad':''}">가격없음 <b>${m.no_price}</b></span>`+
 `<span class="${m.no_img?'bad':''}">이미지없음 <b>${m.no_img}</b></span>`+
 `<span class="${m.no_detail?'bad':''}">상세없음 <b>${m.no_detail}</b></span>`;
document.getElementById('cstat').innerHTML =
 `<span>제품 <b>${c.total.toLocaleString()}</b></span><span>카테고리 <b>${D.current.cats.length}</b>종</span>`+
 `<span>소스 <b>${D.current.srcs.length}</b>곳</span>`+
 `<span class="${c.no_price?'bad':''}">가격없음 <b>${c.no_price}</b></span>`+
 `<span class="${c.no_detail?'bad':''}">상세없음 <b>${c.no_detail}</b></span>`;
document.getElementById('srcLink').href = D.brand_url||'#';

function cards(list, showSrc){
 if(!list.length) return '<div class="empty">해당 항목이 없습니다.</div>';
 return '<div class="grid">'+list.map(p=>`<div class="card">
   <div class="thumb ${p.img?'':'none'}">${p.img?`<img loading="lazy" src="${esc(p.img)}">`:'이미지 없음'}</div>
   <div class="info"><div class="nm">${esc(p.name)}</div>
    <div class="pr">${won(p.price)}</div>
    <div class="cat">${esc(p.cat)}${showSrc&&p.src?' · '+esc(p.src):''}</div>
    <a class="src" href="${esc(p.url)}" target="_blank" rel="noopener">원본 ↗</a></div></div>`).join('')+'</div>';
}

function render(){
 const app=document.getElementById('app');
 if(tab==='cat'){
   const rows=Math.max(D.mirror.cats.length, D.current.cats.length);
   let h=`<p class="note">왼쪽은 <b>KPP 원본 트리 그대로</b>, 오른쪽은 <b>현재 우리 데이터</b>입니다.
     현재는 소스 ${D.current.srcs.length}곳(${D.current.srcs.map(s=>esc(s[0])+' '+s[1]).join(' · ')})이 섞여
     카테고리 축이 ${D.current.cats.length}종으로 흩어져 있습니다.</p>`;
   h+='<table><tr><th>KPP 원본 카테고리</th><th class="num">수</th><th>현재 우리 카테고리</th><th class="num">수</th></tr>';
   for(let i=0;i<rows;i++){
     const a=D.mirror.cats[i], b=D.current.cats[i];
     h+=`<tr><td>${a?esc(a[0]):''}</td><td class="num">${a?a[1]:''}</td>
              <td>${b?esc(b[0]):''}</td><td class="num">${b?b[1]:''}</td></tr>`;
   }
   app.innerHTML=h+'</table>';
 } else if(tab==='onlymir'){
   app.innerHTML=`<p class="note">KPP에는 있는데 <b>우리 사이트에 없는</b> 제품 — 총 <b>${D.diff.only_mirror}</b>개 (최대 400개 표시)</p>`+cards(D.only_mirror_items);
 } else if(tab==='onlycur'){
   app.innerHTML=`<p class="note">우리 데이터에 KPP 출처로 들어와 있으나 <b>지금 KPP 브랜드몰에는 없는</b> 제품 — 총 <b>${D.diff.only_current_kpp}</b>개. 단종·판매중지 의심분입니다. (최대 400개)</p>`+cards(D.only_current_items);
 } else if(tab==='othersrc'){
   app.innerHTML=`<p class="note">KPP가 아닌 <b>다른 소스</b>에서 들어온 제품 — 총 <b>${D.diff.other_source}</b>개. 브랜드를 KPP로 고정 미러링하면 이들이 정리 대상입니다. (최대 400개)</p>`+cards(D.other_src_items,true);
 } else {
   const pd=D.price_diff;
   let h=`<p class="note">양쪽 다 있는 제품 중 <b>가격이 다른</b> 것 — ${pd.length}개 (최대 300개)</p>`;
   if(!pd.length){app.innerHTML=h+'<div class="empty">가격 차이 없음</div>';return;}
   h+='<table><tr><th>제품명</th><th class="num">KPP 원본</th><th class="num">현재 우리</th><th class="num">차이</th><th></th></tr>';
   pd.forEach(p=>{const d=(p.mirror||0)-(p.current||0);
     h+=`<tr><td>${esc(p.name)}</td><td class="num">${won(p.mirror)}</td><td class="num">${won(p.current)}</td>
       <td class="num ${d?'bad':''}">${d?d.toLocaleString():''}</td>
       <td><a class="src" href="${esc(p.url)}" target="_blank">원본 ↗</a></td></tr>`;});
   app.innerHTML=h+'</table>';
 }
}
render();
</script></body></html>
"""


if __name__ == "__main__":
    brand = sys.argv[1] if len(sys.argv) > 1 else "SMALLRIG"
    slug = sys.argv[2] if len(sys.argv) > 2 else brand.lower()
    path, pay = build(brand, slug)
    d = pay["diff"]
    print(f"생성: {path}")
    print(f"  미러링 {pay['mirror']['stats']['total']}개 / 현재 {pay['current']['stats']['total']}개")
    print(f"  겹침 {d['both']} · KPP에만 {d['only_mirror']} · 우리에만(KPP출처) {d['only_current_kpp']} · 타소스 {d['other_source']}")
    print(f"  가격차이 {len(pay['price_diff'])}건")
