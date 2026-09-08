"""Readable rental periods and packing lists derived from verified store data."""
import re


def clean_text(value):
    lines=[]
    for line in str(value or '').replace('\u200b','').replace('\ufeff','').splitlines():
        line=re.sub(r'[ \t\xa0]+',' ',line).strip()
        if line and not re.fullmatch(r'1\.00',line):lines.append(line)
    return '\n'.join(lines)


def presentation(product,detail):
    studio='스튜디오' in product['name'] and '공간대여' in product['name']
    base=product.get('sale_price') if product.get('sale_price') is not None else product.get('price')
    rates=[];issues=[]
    for option in detail.get('options') or []:
        label=clean_text(option.get('name'))
        period=re.search(r'(\d+)\s*시간',label)
        extra=option.get('additional_price',0)
        if not period or not isinstance(base,(int,float)) or not isinstance(extra,(int,float)) or base+extra<0:
            issues.append('unverified_rate');continue
        rates.append({'label':label.replace(' / ',' · '),'hours':int(period[1]),'price':base+extra})
    if not rates:issues.append('missing_period')
    default=next((r for r in rates if r['price']==base),min(rates,key=lambda r:r['price']) if rates else None)
    text=clean_text(detail.get('description_text'))
    # The store sometimes separates the quantity onto the following line.
    joined=re.sub(r'\n(?=//\s*\d)',' ',text)
    components=[];notes=[]
    for line in joined.splitlines():
        if line in ('구성품','구성','포함 구성품'):continue
        match=re.fullmatch(r'(.+?)\s*//\s*(\d+)\s*(?:ea|개)?\s*',line,re.I)
        if match:components.append({'name':match[1].strip(),'quantity':int(match[2])})
        else:notes.append(line)
    conflicts=[]
    for component in components:
        name=component['name']
        if '4702' in product['name'] and '변환' in product['name'] and re.search(r'4702.*monopod',name,re.I):
            conflicts.append({'name':name,'reason':'Plate product is described as a monopod in its source packing list'})
        if 'Atom 2 Action' in product['name'] and 'Atom 2 Pocket Duo' in name:
            conflicts.append({'name':name,'reason':'Action kit title and Pocket Duo packing list conflict'})
    if conflicts:issues.append('packing_list_conflict')
    # Keep the original source text in its source/detail record. Do not present
    # a known conflicting component as verified stock or silently invent one.
    safe_components=[c for c in components if c['name'] not in {v['name'] for v in conflicts}]
    if not components and not studio:issues.append('missing_packing_list')
    summary={'service':'studio' if studio else 'equipment','price':default['price'] if default else base,
        'period':default['label'] if default else None,'rate_count':len(rates)}
    content={'rates':rates,'components':safe_components,'notes':notes,
        'packing_confirmation_required':bool(conflicts) or (not components and not studio),
        'period_confirmation_required':not bool(rates)}
    audit={'product_id':product['id'],'name':product['name'],'issues':issues,'conflicts':conflicts,
        'source_periods':[o.get('name') for o in detail.get('options') or []]}
    return summary,content,audit
