"""Derive NADAUN product details without another dealer's sales invitations.

Source snapshots and manufacturer specifications remain unchanged. Image rules
identify separately reviewed dealer modules, never an entire supplier host.
Manufacturer service disclosures and technical links are not sales invitations.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

RULES_FILE=Path(__file__).with_name('retail-content-rules.json')

def image_key(value):
    parsed=urlsplit(html.unescape(value.strip()))
    host=(parsed.hostname or '').lower().removeprefix('www.')
    return host+unquote(parsed.path)+('?' + parsed.query if parsed.query else '')

@lru_cache(maxsize=1)
def load_rules():
    rules=json.loads(RULES_FILE.read_text())
    if rules.get('schema_version')!=1:raise ValueError('Invalid retail content policy')
    images={}
    for row in rules['images']:
        if not row.get('reason') or not row.get('evidence'):raise ValueError('Unreviewed dealer image')
        key=image_key(row['url'])
        if key in images:raise ValueError('Duplicate dealer image rule: '+key)
        images[key]=row
    text=[(row,re.compile(row['pattern'],re.I)) for row in rules['text']]
    return images,text

def sanitize_detail(product,detail):
    result=deepcopy(detail)
    if product.get('kind')!='purchase':return result,[]
    images,text_rules=load_rules();audit=[]
    for group in ('main','detail'):
        original=result.get('images',{}).get(group,[])
        kept=[]
        for url in original:
            rule=images.get(image_key(url))
            if rule:
                audit.append({'field':'images.'+group,'rule':rule['id'],'url':url,'reason':rule['reason']})
                for note in rule.get('manufacturer_notes',[]):
                    if '*' in note['brands'] or product.get('brand_id') in note['brands']:
                        notes=result.setdefault('manufacturer_service_notes',[])
                        if note['text'] not in notes:notes.append(note['text'])
            else:kept.append(url)
        if group in result.get('images',{}):result['images'][group]=kept
    # A dealer module must never become a gallery/thumbnail fallback.
    thumb=result.get('images',{}).get('thumb')
    if thumb and image_key(thumb) in images:
        replacement=next(iter(result['images'].get('main',[])),None)
        if not replacement:raise ValueError('No real product photo after dealer module removal: '+product['id'])
        result['images']['thumb']=replacement
        audit.append({'field':'images.thumb','rule':images[image_key(thumb)]['id'],'url':thumb})
    for field in ('description_text','description_notice'):
        value=result.get(field,'')
        if not value:continue
        original=value
        for rule,pattern in text_rules:
            value,count=pattern.subn(rule.get('replacement',''),value)
            if count:audit.append({'field':field,'rule':rule['id'],'matches':count,'reason':rule['reason']})
        if value!=original:
            result[field]=re.sub(r'\n{3,}','\n\n',value).strip()
            audit.append({'field':field,'original_sha256':hashlib.sha256(original.encode()).hexdigest(),
                          'cleaned_sha256':hashlib.sha256(result[field].encode()).hexdigest()})
    return result,audit

def assert_clean(product,detail):
    _,audit=sanitize_detail(product,detail)
    if audit:raise ValueError('Dealer sales content remains in public details: '+product['id'])
