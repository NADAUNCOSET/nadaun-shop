"""Resolve retired store images to byte-verified NADAUN storage, offline."""
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
OWN_SITE='S2020100856a601720ff3b'

def retired_asset(url):
    if not isinstance(url,str):return False
    parsed=urlsplit(url)
    return parsed.hostname in ('rainbowshop.imweb.me','rainbowbene.com','www.rainbowbene.com') or (
        parsed.hostname in ('cdn.imweb.me','cdn-optimized.imweb.me') and OWN_SITE in parsed.path)

@lru_cache(maxsize=1)
def asset_map():
    path=ROOT/'_scraper/owned-asset-map.json'
    mapping=json.loads(path.read_text())
    for replacement in mapping.values():
        parsed=urlsplit(replacement)
        if parsed.scheme!='https' or parsed.hostname!='media.nadaun.co' or not parsed.path.startswith('/shop/site-assets/'):
            raise ValueError('Unverified owned asset destination')
    return mapping

def resolve_assets(value,mapping=None):
    mapping=asset_map() if mapping is None else mapping
    if isinstance(value,dict):return {k:resolve_assets(v,mapping) for k,v in value.items()}
    if isinstance(value,list):return [resolve_assets(v,mapping) for v in value]
    if isinstance(value,str):
        if value in mapping:return mapping[value]
        if retired_asset(value):raise ValueError('Retired store asset needs migration before publishing')
    return value
