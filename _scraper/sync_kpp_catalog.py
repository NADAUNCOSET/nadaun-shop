"""KPP catalogue snapshot with independent brand and product category paths.

Uses the existing KPP scraper's observed selectors: .brand_main_menu, #sct,
.sct_txt, .sct_brand and .sit_price. All remote requests are public reads.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup
from sync_shop_sources import KPP, OUT, ROOT, clean, request, save_json, stamp

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NADAUN-catalog-sync/1.0)"}


def fetch(url):
    response = request("GET", url, headers=HEADERS)
    response.encoding = "utf-8"
    # lxml closes KPP's omitted </li> tags. html.parser nests cards, which
    # otherwise incorrectly propagates a later card's sold-out state.
    return BeautifulSoup(response.text, "lxml")


def query(url, field):
    return parse_qs(urlparse(url).query).get(field, [""])[0]


def category_tree(links, scope):
    ordered = {}
    for a in links:
        cid, name = query(a.get("href", ""), "ca_id"), clean(a.get_text(" "))
        if cid and name:
            ordered.setdefault(cid, name)
    result = []
    for cid, name in ordered.items():
        ancestors = sorted((k for k in ordered if cid.startswith(k) and k != cid), key=len)
        result.append({"id": cid, "name": name, "scope": scope,
                       "parent_id": ancestors[-1] if ancestors else None,
                       "path_ids": ancestors + [cid],
                       "path": [ordered[k] for k in ancestors] + [name]})
    return result


def discover():
    home = fetch(KPP + "/")
    categories = category_tree(home.select(".cate_li_1 a[href*='list.php?ca_id=']"), "products")
    if len(categories) < 20:
        raise RuntimeError("KPP global navigation was incomplete")
    brands = {}
    for a in home.select("a[href*='brandmall.php?brand=']"):
        value = query(a["href"], "brand").upper()
        if not value or query(a["href"], "ca_id"):
            continue
        image = a.select_one("img[src]")
        brands.setdefault(value, {"id": value, "name": value, "url": KPP + "/shop/brandmall.php?" + urlencode({"brand": value}),
                                  "logo": urljoin(KPP, image["src"]) if image else ""})
    if len(brands) < 10:
        raise RuntimeError("KPP brand navigation was incomplete")
    for brand in brands.values():
        page = fetch(brand["url"])
        cats = category_tree(page.select(".brand_main_menu a[href*='ca_id=']"), "brand:" + brand["id"])
        if not cats:
            raise RuntimeError(f"Missing KPP brand categories: {brand['name']}")
        brand["category_ids"] = [c["id"] for c in cats]
        categories.extend(cats)
        print(f"KPP navigation: {brand['name']} {len(cats)} categories", flush=True)
        time.sleep(0.1)
    return list(brands.values()), categories


def won_values(node):
    return [int(v.replace(",", "")) for v in re.findall(r"([\d,]+)\s*원", node.get_text(" ", strip=True) if node else "")]


def parse_cards(soup):
    container = soup.select_one("#sct")
    if container is None:
        if "등록된 상품이 없습니다" in soup.get_text(" "):
            return []
        raise RuntimeError("KPP item container was missing")
    products = []
    for item in container.select("li.sct_li"):
        anchor = item.select_one(".sct_txt a[href*='it_id=']")
        if not anchor:
            raise RuntimeError("KPP product card has no item link")
        iid = query(anchor["href"], "it_id")
        if not iid.isdigit():
            raise RuntimeError("Invalid KPP product ID")
        image = item.select_one(".sct_img > a > img")
        brand = item.select_one(".sct_brand")
        prices = won_values(item.select_one(".sct_cost"))
        soldout = item.select_one(".stock_yn")
        products.append({
            "id": "kpp-" + iid, "source": "kpp", "source_id": iid,
            "name": clean(anchor.get_text(" ")), "brand": clean(brand.get_text()) if brand else "",
            "source_url": urljoin(KPP, anchor["href"]), "price": prices[0] if prices else None,
            "sale_price": prices[-1] if prices else None,
            "supplier_status": "soldout" if soldout and "sold" in soldout.get_text().lower() else "listed",
            "kind": "purchase",
            "images": {"thumb": urljoin(KPP, image["src"]) if image else "", "main": [], "detail": []},
            "brand_category_ids": [], "product_category_ids": [], "brand_mall_ids": [],
        })
    return products


def collect_category(cid):
    # KPP's default order is randomized between requests, causing missing and
    # repeated products across pages. Use its visible '최근등록순' sort link.
    url = KPP + "/shop/list.php?" + urlencode({"ca_id": cid, "sort": "it_time", "sortodr": "desc"})
    first = fetch(url)
    pages = [int(query(a["href"], "page")) for a in first.select(".pg_wrap a[href]") if query(a["href"], "page").isdigit()]
    last_page = max([1] + pages)
    if last_page > 1000:
        raise RuntimeError("Unexpected KPP page count")
    products = {}
    for page_no in range(1, last_page + 1):
        soup = first if page_no == 1 else fetch(url + "&page=" + str(page_no))
        cards = parse_cards(soup)
        if page_no > 1 and not cards:
            raise RuntimeError(f"KPP category {cid} ended before its advertised last page")
        for card in cards:
            if card["id"] in products:
                raise RuntimeError(f"Repeated KPP product across pages of {cid}")
            products[card["id"]] = card
        time.sleep(0.06)
    return cid, products, last_page


def collect():
    brands, categories = discover()
    by_id = {}
    for cat in categories:
        by_id.setdefault(cat["id"], []).append(cat)
    all_products, category_counts = {}, {}
    page_count = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(collect_category, cid): cid for cid in by_id}
        for n, future in enumerate(as_completed(futures), 1):
            cid, products, pages = future.result()
            category_counts[cid] = len(products)
            page_count += pages
            for pid, product in products.items():
                saved = all_products.setdefault(pid, product)
                for cat in by_id[cid]:
                    key = "product_category_ids" if cat["scope"] == "products" else "brand_category_ids"
                    for category_id in cat["path_ids"]:
                        if category_id not in saved[key]:
                            saved[key].append(category_id)
                    if cat["scope"].startswith("brand:"):
                        mall = cat["scope"].split(":", 1)[1]
                        if mall not in saved["brand_mall_ids"]:
                            saved["brand_mall_ids"].append(mall)
            if n == 1 or n % 20 == 0 or n == len(futures):
                print(f"KPP lists: {n}/{len(futures)} categories, {page_count} pages, {len(all_products):,} unique products", flush=True)
    if len(all_products) < 3000:
        raise RuntimeError("KPP inventory is unexpectedly small; keep the previous published snapshot")
    # Preserve already downloaded product detail assets without editing their
    # original brand databases. A later detail pass refreshes source changes.
    for file in (ROOT / "data" / "products").glob("*.json"):
        old = json.loads(file.read_text(encoding="utf-8"))
        for pid, old_product in old.get("products", {}).items():
            if pid not in all_products or old_product.get("source") != "kpp":
                continue
            images = old_product.get("images") or {}
            all_products[pid]["images"]["main"] = images.get("main") or []
            all_products[pid]["images"]["detail"] = images.get("detail") or []
            all_products[pid]["detail_status"] = "existing_assets_pending_refresh"
    final_nav = fetch(KPP + "/")
    final_ids = {query(a["href"], "brand").upper() for a in final_nav.select("a[href*='brandmall.php?brand=']") if not query(a["href"], "ca_id")}
    if set(b["id"] for b in brands) != final_ids:
        raise RuntimeError("KPP brand menu changed during collection; rerun before publishing")
    out = {"source": "kpp", "source_url": KPP, "collected_at": stamp(), "complete": True,
           "product_count": len(all_products), "page_count": page_count,
           "brands": brands, "categories": categories, "category_counts": category_counts,
           "products": dict(sorted(all_products.items()))}
    save_json(OUT / "kpp.json", out)
    print(f"KPP verified: {len(brands)} brand malls, {len(categories)} category entries, {len(all_products):,} products", flush=True)
    return out


if __name__ == "__main__":
    collect()
