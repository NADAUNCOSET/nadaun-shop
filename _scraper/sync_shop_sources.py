"""Read-only source imports for NADAUN Shop; credentials stay in the NAS hub.

Run with the local nadaun-shop Python environment. This command reads remote
catalogues and writes only this project's new data/catalog/sources directory.
It never runs the order automation or writes to a supplier/merchant API.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import threading
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import bcrypt
from bs4 import BeautifulSoup
from dotenv import dotenv_values
import requests

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT.parents[1] / "_claude"
OUT = ROOT / "data" / "catalog" / "sources"
NAVER = "https://api.commerce.naver.com/external"
KPP = "https://kppkpp.co.kr"
STORE = "https://smartstore.naver.com/rainbowbene"
_naver_rate_lock = threading.Lock()
_naver_next_read = 0.0


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".catalog-", suffix=".tmp", delete=False) as f:
        f.write(text)
        temp = f.name
    os.replace(temp, path)


def request(method, url, **kwargs):
    """Bounded retries; errors never include auth query parameters or tokens."""
    for attempt in range(5):
        if method == 'GET' and url.startswith(NAVER + '/v2/products/origin-products/'):
            # Verified API headers advertise two detail reads per second.
            global _naver_next_read
            with _naver_rate_lock:
                time.sleep(max(0, _naver_next_read - time.monotonic()))
                _naver_next_read = time.monotonic() + 0.52
        try:
            response = requests.request(method, url, timeout=(8, 35), **kwargs)
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 4:
                raise RuntimeError(f"Source connection failed: {urlparse(url).netloc}") from None
            time.sleep(min(2 ** attempt, 8))
            continue
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
            time.sleep(min(int(response.headers.get("Retry-After", 2 ** attempt)), 15))
            continue
        if not response.ok:
            raise RuntimeError(f"Source returned HTTP {response.status_code}: {urlparse(url).netloc}{urlparse(url).path}")
        return response
    raise RuntimeError("Source retry limit reached")


def credentials():
    path = HUB / "nadaun_order_sync" / ".env"
    if not path.is_file():
        raise RuntimeError("NAS commerce credentials are unavailable")
    return dotenv_values(path)


def naver_headers():
    cfg = credentials()
    # Same SELF auth protocol as nadaun_order_sync.daily_check.naver_get_token.
    cid, secret = cfg["NAVER_CLIENT_ID"], cfg["NAVER_CLIENT_SECRET"]
    ts = str(int(time.time() * 1000))
    sig = base64.b64encode(bcrypt.hashpw(f"{cid}_{ts}".encode(), secret.encode())).decode()
    response = request("POST", NAVER + "/v1/oauth2/token", data={
        "client_id": cid, "timestamp": ts, "client_secret_sign": sig,
        "grant_type": "client_credentials", "type": "SELF",
    }).json()
    headers = {"Authorization": "Bearer " + response["access_token"]}
    channels = request("GET", NAVER + "/v1/seller/channels", headers=headers).json()
    if not any(c.get("url", "").rstrip("/") == STORE for c in channels):
        raise RuntimeError("The API account is not the requested rainbowbene store")
    return headers


def naver_public_product(channel):
    if channel.get("channelServiceType") != "STOREFARM":
        return None
    if channel.get("channelProductDisplayStatusType") != "ON":
        return None
    if channel.get("statusType") not in ("SALE", "OUTOFSTOCK"):
        return None
    pid = str(channel["channelProductNo"])
    name = clean(channel.get("name"))
    return {
        "id": "smartstore-" + pid,
        "source": "smartstore", "source_id": pid,
        "origin_id": str(channel["originProductNo"]),
        "name": name,
        "brand": clean(channel.get("brandName") or channel.get("manufacturerName")),
        "manufacturer": clean(channel.get("manufacturerName")),
        "source_url": STORE + "/products/" + pid,
        "price": channel.get("salePrice"),
        "sale_price": channel.get("discountedPrice", channel.get("salePrice")),
        "status": "soldout" if channel["statusType"] == "OUTOFSTOCK" else "sale",
        "kind": "rental" if re.search(r"^\[\s*(대여|렌탈)\b", name) else "purchase",
        "images": {"thumb": (channel.get("representativeImage") or {}).get("url", ""), "main": [], "detail": []},
        "source_category_id": channel.get("categoryId"),
        "source_category_ids": channel.get("wholeCategoryId", "").split(">"),
        "source_category_path": channel.get("wholeCategoryName", "").split(">"),
        "source_modified_at": channel.get("modifiedDate"),
    }


def collect_smartstore():
    headers = naver_headers()
    products, counts, ids = {}, Counter(), set()
    page = 1
    expected = None
    while True:
        body = request("POST", NAVER + "/v1/products/search", headers=headers, json={"page": page, "size": 100}).json()
        total = body["totalElements"]
        if expected is None:
            expected = total
        elif total != expected:
            raise RuntimeError("Smartstore inventory changed during pagination; rerun before publishing")
        for item in body["contents"]:
            oid = str(item["originProductNo"])
            if oid in ids:
                raise RuntimeError("Repeated Smartstore origin product during pagination")
            ids.add(oid)
            for ch in item.get("channelProducts", []):
                counts[f"{ch.get('statusType')}/{ch.get('channelProductDisplayStatusType')}"] += 1
                product = naver_public_product(ch)
                if product:
                    products[product["id"]] = product
        if page == 1 or page % 10 == 0 or body.get("last"):
            print(f"Smartstore: page {page}/{body['totalPages']}, public products {len(products):,}", flush=True)
        if body.get("last"):
            break
        page += 1
        time.sleep(0.18)
    if len(ids) != expected:
        raise RuntimeError(f"Smartstore origin count mismatch: {len(ids)} != {expected}")
    check = request("POST", NAVER + "/v1/products/search", headers=headers, json={"page": 1, "size": 1}).json()
    if check["totalElements"] != expected:
        raise RuntimeError("Smartstore final inventory re-query did not match")
    out = {"source": "smartstore", "source_url": STORE, "collected_at": stamp(),
           "complete": True, "origin_count": expected, "product_count": len(products),
           "status_counts": dict(counts), "products": products}
    save_json(OUT / "smartstore.json", out)
    print(f"Smartstore verified: {len(products):,} public products ({expected:,} origin records)", flush=True)
    return out




def flatten_categories(nodes, parents=()):
    result = []
    for node in nodes:
        path = (*parents, {"id": node["code"], "name": node["name"]})
        result.append({"id": node["code"], "name": node["name"], "parent_id": parents[-1]["id"] if parents else None,
                       "path": [n["name"] for n in path], "path_ids": [n["id"] for n in path]})
        result.extend(flatten_categories(node.get("list", []), path))
    return result


def imweb_public_price(item):
    price = item.get('price')
    if not isinstance(price, (int, float)) or item.get('price_none'):
        return None
    if 'period' not in (item.get('product_discount_options') or []):
        return price
    # API returns currently applicable period discounts. Member-only prices
    # must not become the anonymous storefront price.
    for discount in item.get('period_discount_data') or []:
        if discount.get('group_type') != '비회원+회원':
            continue
        amount = float(discount.get('dc_price') or 0)
        if discount.get('dc_type') == 'price':
            return max(0, price - int(amount))
        if discount.get('dc_type') == 'percent':
            return max(0, int(price * (100 - amount) / 100))
    return price




def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=["smartstore"])
    args = parser.parse_args()
    collect_smartstore()


if __name__ == "__main__":
    main()
