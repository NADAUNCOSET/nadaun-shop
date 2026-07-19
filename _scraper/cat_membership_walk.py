# -*- coding: utf-8 -*-
"""리프 카테고리 멤버십 워크 — 각 소스의 모든 리프 카테고리 리스트 페이지를 걸어
   제품 sid → 가장 깊은 카테고리 매핑을 만들어 data/_catwalk_<site>.json 저장 (2026-07-20).
   상세페이지 재스크랩 없음(리스트만). 이후 rebuild_cat_paths.py --apply가 이 맵을 우선 사용.
   실행: python cat_membership_walk.py cafe24 | firstmall | godo | makeshop | <site명...>"""
import sys, io, re, json, time
from pathlib import Path
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception: pass
HERE = Path(__file__).parent; sys.path.insert(0, str(HERE))
ROOT = HERE.parent; OUT = ROOT / "data"

_KEEP = []
def mod(name):
    _KEEP.append(sys.stdout)
    return __import__(name)

def save(site, membership, paths):
    json.dump({"membership": membership, "paths": paths},
              open(OUT / f"_catwalk_{site}.json", "w", encoding="utf-8"), ensure_ascii=False)
    multi = sum(1 for c in membership.values() if len(paths.get(c, [])) > 1)
    print(f"  → _catwalk_{site}.json (제품 {len(membership)}, 2단계+ {multi})", flush=True)

# ── firstmall/godo: 세그먼트 코드 리프 워크 ─────────────────────
def walk_seg(M, site, base, seg, ajax=False):
    cats = M.fetch_nav(base)
    codes = sorted(cats)
    leaves = [c for c in codes if not any(o != c and o.startswith(c) for o in codes)]
    skip = ("개인결제", "상품명", "고객결제")
    leaves = [c for c in leaves if not any(s in cats.get(c, "") for s in skip)]
    paths = {c: [cats[c[:i]] for i in range(seg, len(c) + 1, seg) if cats.get(c[:i])] for c in codes}
    membership = {}
    for n, c in enumerate(sorted(leaves, key=len, reverse=True), 1):   # 깊은 리프 우선
        try:
            items = M.list_items(base, c, ajax=ajax) if "ajax" in M.list_items.__code__.co_varnames \
                    else M.list_items(base, c)
        except Exception as e:
            print(f"  ! {site}/{c} 리스트 실패: {e}", flush=True); continue
        for sid in items:
            membership.setdefault(str(sid), c)
        if n % 20 == 0: print(f"  … {site} 리프 {n}/{len(leaves)} (매핑 {len(membership)})", flush=True)
        time.sleep(0.3)
    save(site, membership, paths)

# ── cafe24: breadcrumb로 트리 구성 → 리프 워크 ──────────────────
CRUMB_SELS = ["ul.xans-product-headcategory li a", ".xans-product-headcategory a",
              ".path li a", ".path a", "#titleArea .headCategory a"]
def walk_cafe24(C24, site, base):
    cats = C24.fetch_nav(base)
    paths = {}
    for n, c in enumerate(sorted(cats), 1):
        try:
            soup = C24.BeautifulSoup(C24.get(f"{base}/product/list.html?cate_no={c}").text, "html.parser")
            p = []
            for sel in CRUMB_SELS:
                names = [C24.clean(a.get_text()) for a in soup.select(sel)]
                names = [x for x in names if x and x not in ("홈", "HOME", "Home", ">")]
                if names: p = names; break
            paths[c] = p or [cats[c]]
        except Exception:
            paths[c] = [cats[c]]
        if n % 30 == 0: print(f"  … {site} 경로 {n}/{len(cats)}", flush=True)
        time.sleep(0.3)
    tuples = {c: tuple(p) for c, p in paths.items()}
    leaves = [c for c, t in tuples.items()
              if not any(o != c and len(tuples[o]) > len(t) and tuples[o][:len(t)] == t for o in tuples)]
    membership = {}
    for n, c in enumerate(sorted(leaves, key=lambda x: -len(tuples[x])), 1):
        try: items = C24.list_items(base, c)
        except Exception as e:
            print(f"  ! {site}/{c} 리스트 실패: {e}", flush=True); continue
        for sid in items: membership.setdefault(str(sid), c)
        if n % 20 == 0: print(f"  … {site} 리프 {n}/{len(leaves)} (매핑 {len(membership)})", flush=True)
        time.sleep(0.3)
    save(site, membership, paths)

# ── makeshop(plthink): xcode-mcode 2단 워크 ────────────────────
def walk_makeshop(MS, site, base):
    cats = MS.fetch_nav(base)   # {"x" | "x-m": {href,name}}
    paths, membership = {}, {}
    subs = [k for k in cats if "-" in k]
    tops = {k: v["name"] for k, v in cats.items() if "-" not in k}
    for k in cats:
        if "-" in k:
            x = k.split("-")[0]
            paths[k] = [tops.get(x, ""), cats[k]["name"]]
            paths[k] = [p for p in paths[k] if p]
        else:
            paths[k] = [cats[k]["name"]]
    walk = subs or list(cats)
    for n, k in enumerate(walk, 1):
        try: items = MS.list_items(base, cats[k]["href"])
        except Exception as e:
            print(f"  ! {site}/{k} 리스트 실패: {e}", flush=True); continue
        for sid in items: membership.setdefault(str(sid), k)
        if n % 20 == 0: print(f"  … {site} {n}/{len(walk)} (매핑 {len(membership)})", flush=True)
        time.sleep(0.3)
    save(site, membership, paths)

if __name__ == "__main__":
    args = sys.argv[1:] or ["cafe24"]
    if "cafe24" in args or any(a in ("hktools","sama","benro","mustcolor","fomex","ldnet","cinemall","bando") for a in args):
        C24 = mod("cafe24")
        targets = [a for a in args if a in C24.SITES] or list(C24.SITES)
        for s in targets:
            print(f"[cafe24/{s}] 워크 시작", flush=True)
            walk_cafe24(C24, s, C24.SITES[s]["base"])
    if "firstmall" in args or any(a in ("avx","aurora","sajin","green") for a in args):
        FM = mod("firstmall")
        targets = [a for a in args if a in FM.SITES] or list(FM.SITES)
        for s in targets:
            print(f"[firstmall/{s}] 워크 시작", flush=True)
            walk_seg(FM, s, FM.SITES[s]["base"], 4, ajax=FM.SITES[s].get("ajax_list", False))
    if "godo" in args or any(a in ("redsun","calla","lmount") for a in args):
        GD = mod("godo")
        targets = [a for a in args if a in GD.SITES] or list(GD.SITES)
        for s in targets:
            print(f"[godo/{s}] 워크 시작", flush=True)
            walk_seg(GD, s, GD.SITES[s]["base"], 3)
    if "makeshop" in args or "plthink" in args:
        MS = mod("makeshop")
        for s in (MS.SITES if hasattr(MS, "SITES") else {"plthink": None}):
            print(f"[makeshop/{s}] 워크 시작", flush=True)
            walk_makeshop(MS, s, MS.SITES[s]["base"])
    print("WALK DONE", flush=True)
