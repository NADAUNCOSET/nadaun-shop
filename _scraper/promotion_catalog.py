"""Attach evidence-backed, time-bounded promotions without inventing prices."""
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
import json,re

def instant(value):
    if not isinstance(value,str):raise ValueError('Promotion timestamp missing')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('Promotion timestamps must include timezone')
    return result

def validate_campaign(campaign):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,95}',campaign.get('id','')):raise ValueError('Invalid promotion identity')
    if campaign.get('type') not in ('price_discount','cashback','gift','supplier_event'):raise ValueError('Unsupported promotion benefit')
    if instant(campaign['start_at'])>=instant(campaign['end_at']):raise ValueError('Promotion period is invalid')
    if not campaign.get('title') or not campaign.get('source') or not re.fullmatch(r'[a-f0-9]{64}',campaign.get('evidence_sha256','')):raise ValueError('Promotion source evidence missing')
    instant(campaign['observed_at'])
    if urlsplit(campaign.get('source_url','')).scheme!='https':raise ValueError('Promotion source URL is unsafe')
    if not isinstance(campaign.get('source_product_ids'),list) or not campaign['source_product_ids']:raise ValueError('Exact source product matching is required')
    if any(not isinstance(pid,str) or not pid.startswith(campaign['source']+'-') for pid in campaign['source_product_ids']):raise ValueError('Promotion product must belong to its verified source')
    if len(set(campaign['source_product_ids']))!=len(campaign['source_product_ids']):raise ValueError('Duplicate promotion source product')
    return campaign

def apply_promotions(products,categories,registry):
    campaigns=registry.get('campaigns',[]);seen=set()
    for campaign in campaigns:
        validate_campaign(campaign)
        if campaign['id'] in seen:raise ValueError('Duplicate promotion campaign')
        seen.add(campaign['id']);cid='promotion:'+campaign['id'];matched=[];targets=set(campaign['source_product_ids'])
        for p in products.values():
            if p.get('kind')!='purchase' or p.get('hidden'):continue
            offers=p.get('offers') or [{'id':p['id'],'source':p.get('source')}]
            if any(o.get('source')==campaign['source'] and o.get('id') in targets for o in offers):
                p.setdefault('promotions',[]).append({k:campaign[k] for k in ['id','title','type','source','source_url','start_at','end_at','observed_at','evidence_sha256'] if k in campaign}|{'terms':campaign.get('terms','')})
                p.setdefault('promotion_ids',[]).append(cid);matched.append(p['id'])
        if not matched:raise ValueError('Promotion does not match a verified published source product: '+campaign['id'])
        categories[cid]={'id':cid,'name':campaign['title'],'parent_id':None,'brand_id':None,'scope':'collection','navigation_role':'collection','count':len(matched)}
    return campaigns

def consignment_used(product):
    return (product.get('kind')=='purchase' and any(o.get('source')=='smartstore' for o in product.get('offers',[])) and
            bool(re.match(r'^\s*(?:\[(?:중고|위탁|위탁중고)\]|(?:중고|위탁중고)\s*[:：])',product.get('name',''))))
