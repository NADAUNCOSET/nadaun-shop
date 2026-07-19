# -*- coding: utf-8 -*-
"""카테고리 트리 복원 — 저장된 cate_no로 각 소스 사이트의 대>중>소 전체 경로 재구성 (2026-07-20 대표 지시).
   제품 재스크랩 없이 카테고리 메타만 재파싱해 cat_path를 원본 트리로 교체.
   - firstmall(avx/aurora/sajin/green): 코드 4자리 세그먼트 = 계층. fetch_nav 이름 매핑.
   - godo(redsun/calla/lmount): cateCd 3자리 세그먼트 = 계층.
   - cafe24(hktools 등): 카테고리 리스트 페이지 1회 fetch → breadcrumb 파싱.
   - saeki: data/_saeki_categories.json(대분류) + 저장된 소분류명 2단.
   - tov: WooCommerce Store API categories 트리 + 제품별 categories.
   - 제외: kpp(이미 정상), tilta.com/clmedia/plthink(별도 처리).
   실행: python rebuild_cat_paths.py [--apply]   (기본=dry-run 리포트만)"""
import sys, io, re, json, time, collections
from pathlib import Path
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception: pass

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
DATA = ROOT / "data" / "products"
APPLY = "--apply" in sys.argv

import requests
from bs4 import BeautifulSoup
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36"}
S = requests.Session(); S.headers.update(UA)

def get(u):
    for k in range(3):
        try:
            r = S.get(u, timeout=40)
            r.encoding = r.apparent_encoding if len(r.content) < 1_000_000 else "utf-8"
            return r
        except Exception:
            time.sleep(3 * (k + 1))
    raise RuntimeError(f"get 실패: {u}")

def clean(t): return re.sub(r"\s+", " ", (t or "").strip())

# ── 세그먼트 코드 계열 (firstmall=4자리, godo=3자리) ─────────────
def seg_paths(cate_nos, cats, seg):
    """계층코드 → [대,중,소] 이름 경로. cats={code:name}."""
    out = {}
    for c in cate_nos:
        path = []
        for i in range(seg, len(c) + 1, seg):
            nm = cats.get(c[:i], "")
            if nm: path.append(nm)
        out[c] = path
    return out

def firstmall_handler(site, base, cate_nos):
    import firstmall as FM
    return seg_paths(cate_nos, FM.fetch_nav(base), 4)

def godo_handler(site, base, cate_nos):
    import godo as GD
    return seg_paths(cate_nos, GD.fetch_nav(base), 3)

# ── cafe24: 카테고리 페이지 breadcrumb ──────────────────────────
CRUMB_SELS = ["ul.xans-product-headcategory li a", ".xans-product-headcategory a",
              ".path li a", ".path a", "#titleArea .headCategory a"]
def cafe24_handler(site, base, cate_nos):
    out = {}
    for n, c in enumerate(sorted(cate_nos), 1):
        try:
            soup = BeautifulSoup(get(f"{base}/product/list.html?cate_no={c}").text, "html.parser")
            path = []
            for sel in CRUMB_SELS:
                names = [clean(a.get_text()) for a in soup.select(sel)]
                names = [x for x in names if x and x not in ("홈", "HOME", "Home", ">")]
                if names: path = names; break
            if not path:   # breadcrumb 없으면 타이틀 h2
                h = soup.select_one("#titleArea h2, .titleArea h2, h2.title")
                if h: path = [clean(h.get_text())]
            out[c] = path
        except Exception as e:
            out[c] = []
        if n % 30 == 0: print(f"    … {site} {n}/{len(cate_nos)}", flush=True)
        time.sleep(0.4)
    return out

# ── saeki: 로컬 덤프 2단 ────────────────────────────────────────
def saeki_handler(site, base, cate_nos):
    cats = json.load(open(ROOT / "data" / "_saeki_categories.json", encoding="utf-8"))
    return {c: ([cats[c]] if c in cats else []) for c in cate_nos}

# ── tov: WooCommerce Store API ─────────────────────────────────
def tov_handler(site, base, cate_nos):
    cats = {}
    page = 1
    while True:
        r = get(f"{base}/wp-json/wc/store/v1/products/categories?per_page=100&page={page}")
        arr = r.json()
        if not arr: break
        for c in arr: cats[c["id"]] = (clean(BeautifulSoup(c["name"], "html.parser").get_text()), c.get("parent", 0))
        if len(arr) < 100: break
        page += 1
    def path_of(cid):
        p = []
        while cid and cid in cats:
            nm, parent = cats[cid]
            p.insert(0, nm); cid = parent
        return p
    # 제품별 categories → data의 tov 제품 pid→path (cate_no가 비어있어 별도 매핑)
    prod_paths = {}
    page = 1
    while True:
        r = get(f"{base}/wp-json/wc/store/v1/products?per_page=100&page={page}")
        arr = r.json()
        if not arr: break
        for p in arr:
            cs = p.get("categories") or []
            best = max((path_of(c["id"]) for c in cs), key=len, default=[])
            prod_paths[f"tov-{p['id']}"] = best
        print(f"    … tov 제품 p{page} ({len(prod_paths)}개)", flush=True)
        if len(arr) < 100: break
        page += 1; time.sleep(0.3)
    return {"__by_pid__": prod_paths}

# ── 메인 ───────────────────────────────────────────────────────
_KEEP = []   # 각 스크래퍼 모듈이 sys.stdout을 재래핑 → 이전 래퍼 GC가 공유 버퍼를 닫는 것 방지
def site_bases():
    _KEEP.append(sys.stdout); import firstmall as FM
    _KEEP.append(sys.stdout); import godo as GD
    _KEEP.append(sys.stdout); import cafe24 as C24
    bases = {}
    for s, v in FM.SITES.items(): bases[s] = (v["base"], firstmall_handler)
    for s, v in GD.SITES.items(): bases[s] = (v["base"], godo_handler)
    for s, v in C24.SITES.items(): bases[s] = (v["base"], cafe24_handler)
    bases["saeki"] = ("https://www.saeki.co.kr", saeki_handler)
    bases["tov"] = ("https://tovmall.co.kr", tov_handler)
    return bases

if __name__ == "__main__":
    bases = site_bases()
    # 소스별 사용 중인 cate_no 수집 (tov는 cate_no가 비어 있어도 API 핸들러 강제 포함)
    by_site = collections.defaultdict(set)
    files = list(DATA.glob("*.json"))
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        for v in d.get("products", {}).values():
            s, c = v.get("source"), v.get("cate_no")
            if s in bases and c: by_site[s].add(str(c))
            elif s == "tov": by_site["tov"]   # 존재만 등록
    # 사이트별 경로 맵 구축 — 멤버십 워크 결과(_catwalk_<site>.json)가 있으면 그것을 우선 사용
    maps, walks = {}, {}
    for s in sorted(by_site):
        wf = ROOT / "data" / f"_catwalk_{s}.json"
        if wf.exists():
            w = json.load(open(wf, encoding="utf-8"))
            walks[s] = w
            maps[s] = {c: p for c, p in w["paths"].items()}
            print(f"[{s}] 워크 결과 사용 (멤버십 {len(w['membership'])}개)", flush=True)
            continue
        base, handler = bases[s]
        print(f"[{s}] 카테고리 {len(by_site[s])}개 경로 복원 중…", flush=True)
        try: maps[s] = handler(s, base, by_site[s])
        except Exception as e:
            print(f"  !! {s} 실패: {e}", flush=True); maps[s] = {}
    # 적용/리포트
    stat = collections.defaultdict(lambda: [0, 0, 0])   # site: [제품수, 경로복원, 다단계]
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        changed = False
        for pid, v in d.get("products", {}).items():
            s = v.get("source")
            if s not in maps: continue
            m = maps[s]
            if s in walks:   # 멤버십 워크: sid→리프코드→경로, 없으면 기존 cate_no 경로
                sid = str(v.get("source_id", ""))
                code = walks[s]["membership"].get(sid) or str(v.get("cate_no") or "")
                path = m.get(code)
            else:
                path = (m.get("__by_pid__", {}).get(pid) if "__by_pid__" in m
                        else m.get(str(v.get("cate_no") or "")))
            stat[s][0] += 1
            if not path: continue
            if s == "saeki" and v.get("category") and v["category"] not in path:
                path = path + [v["category"]]   # 대분류 + 저장된 소분류명
            stat[s][1] += 1
            if len(path) > 1: stat[s][2] += 1
            if v.get("cat_path") != path:
                v["cat_path"] = path; v["category"] = path[-1]; changed = True
        if APPLY and changed:
            json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    mode = "APPLY" if APPLY else "DRY-RUN"
    print(f"\n=== {mode} 결과 (제품수 / 경로복원 / 2단계이상) ===")
    for s in sorted(stat):
        t, ok, multi = stat[s]
        print(f"  {s:<10} {t:>6} / {ok:>6} / {multi:>6}")
