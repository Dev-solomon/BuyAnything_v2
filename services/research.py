import json, os, re
from collections import OrderedDict
from openai import OpenAI
from services.cj import search_products, product_detail, variants, storefront_url


def _client(): return OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
def _json(text): return json.loads(text.strip().replace('```json','').replace('```',''))

def research_trending_products():
    if not os.getenv('OPENAI_API_KEY'):
        return [{'name':f'Demo Product {i}','reason':'Add OPENAI_API_KEY to enable live AI web research.','trend_score':101-i,'supplier_search_query':'home gadget'} for i in range(1,21)]
    prompt='''Research ecommerce products showing strong consumer buying/demand momentum during roughly the last 14-30 days. Return exactly 20 physical, ad-friendly products, ranked best to weakest. Avoid regulated/unsafe goods, weapons, alcohol, nicotine, gambling, adult goods, prescription/medical claims and counterfeits. For each return name, reason grounded in recent signals, trend_score 1-100, and supplier_search_query suitable for CJdropshipping. JSON only: {"products":[...]}. Never invent exact sales figures.'''
    r=_client().responses.create(model=os.getenv('OPENAI_MODEL','gpt-5.6-luna'),tools=[{'type':'web_search'}],input=prompt)
    return _json(r.output_text)['products'][:20]

def _margin_price(cost):
    try: cost=float(str(cost).split('-')[0])
    except: cost=10
    return round((cost*3)+16,2)

_LABEL_ALIASES={
    'colour':'Color','color':'Color','colors':'Color','colours':'Color',
    'size':'Size','sizes':'Size','shoe size':'Size','shoesize':'Size',
    'style':'Style','styles':'Style','type':'Style','pattern':'Style',
    'model':'Model','models':'Model','model number':'Model',
    'material':'Material','materials':'Material','specification':'Specification','spec':'Specification',
    'capacity':'Capacity','volume':'Capacity','length':'Length','width':'Width','pack':'Pack','quantity':'Pack'
}

def _clean_label(label):
    label=re.sub(r'[_-]+',' ',str(label or '')).strip()
    return _LABEL_ALIASES.get(label.lower(), label.title() if label else '')

def _attributes_from_variant(v):
    """Normalize CJ's different variant payload shapes into friendly label/value pairs."""
    attrs=OrderedDict()
    # Newer CJ payloads can expose property/option arrays or dictionaries.
    for key in ('variantProperty','variantProperties','propertyList','properties','attributes','options'):
        raw=v.get(key)
        if isinstance(raw,dict):
            for k,val in raw.items():
                if val not in (None,''):
                    attrs[_clean_label(k)]=str(val).strip()
        elif isinstance(raw,list):
            for item in raw:
                if not isinstance(item,dict): continue
                label=item.get('propertyName') or item.get('name') or item.get('key') or item.get('attributeName') or item.get('variantName')
                val=item.get('propertyValue') or item.get('value') or item.get('attributeValue') or item.get('variantValue')
                if label and val not in (None,''): attrs[_clean_label(label)]=str(val).strip()
    # Some CJ responses provide parallel property name/value strings.
    names=v.get('variantPropertyName') or v.get('propertyName')
    values=v.get('variantPropertyValue') or v.get('propertyValue')
    if isinstance(names,str) and isinstance(values,str):
        ns=[x.strip() for x in re.split(r'[,;/|]+',names) if x.strip()]
        vs=[x.strip() for x in re.split(r'[,;/|]+',values) if x.strip()]
        if len(ns)==len(vs):
            for k,val in zip(ns,vs): attrs[_clean_label(k)]=val
    return dict(attrs)

def _friendly_variant(v):
    attrs=_attributes_from_variant(v)
    raw=str(v.get('variantKey') or v.get('variantNameEn') or v.get('variantName') or v.get('variantSku') or 'Default').strip()
    # If CJ doesn't identify dimensions explicitly, keep its exact variant description as a safe Style selector.
    if not attrs and raw and raw.lower()!='default': attrs={'Style':raw}
    name=' / '.join(str(x) for x in attrs.values()) if attrs else raw
    return attrs, name or 'Default'

def _build_option_schema(normalized):
    schema=[]
    labels=[]
    for v in normalized:
        for label in v.get('attributes',{}):
            if label not in labels: labels.append(label)
    for label in labels:
        values=[]
        for v in normalized:
            val=v.get('attributes',{}).get(label)
            if val and val not in values: values.append(val)
        if values: schema.append({'key':label.lower().replace(' ','_'),'label':label,'values':values})
    return schema

def build_product(candidate):
    q=candidate.get('supplier_search_query') or candidate.get('name'); matches=search_products(q,8)
    if not matches: raise RuntimeError(f'No CJdropshipping products matched “{q}”. Try another candidate/search phrase.')
    best=max(matches,key=lambda x:(int(x.get('listedNum') or 0),int(x.get('warehouseInventoryNum') or 0)))
    pid=best['id']; detail=product_detail(pid); vs=variants(pid)
    if not vs: raise RuntimeError('CJ product has no orderable variants.')
    normalized=[]
    for v in vs:
        try: cost=float(v.get('variantSellPrice') or best.get('sellPrice') or 10)
        except: cost=10.0
        attrs,name=_friendly_variant(v)
        normalized.append({'vid':str(v.get('vid') or ''),'sku':v.get('variantSku'),'name':name,'attributes':attrs,'image':v.get('variantImage') or '', 'supplier_cost':cost,'retail_price':_margin_price(cost)})
    normalized=[v for v in normalized if v['vid']]
    if not normalized: raise RuntimeError('CJ product variants did not include orderable variant IDs.')
    chosen=min(normalized,key=lambda v:v['supplier_cost']); cost=chosen['supplier_cost']; price=chosen['retail_price']; compare=round(price*1.28+.01,2)
    raw_desc=re.sub('<[^>]+>',' ',str(detail.get('description') or best.get('description') or ''))
    copy={'tagline':'A smart everyday upgrade, selected for usefulness and value.','description':raw_desc[:650] or best.get('nameEn',''),'benefits':['Practical design for everyday use','Selected from an established fulfillment catalog','Secure checkout with tracked order processing']}
    if os.getenv('OPENAI_API_KEY'):
        prompt=f'''Write elegant, factual conversion copy for this CJdropshipping product. Product: {best.get('nameEn')}. Supplier description: {raw_desc[:2500]}. Return JSON only with tagline (max 18 words), description (60-100 words), benefits (exactly 3 short strings). Do not invent reviews, certifications, scarcity, shipping times, guarantees, health claims, materials, or capabilities not present in the supplied facts.'''
        r=_client().responses.create(model=os.getenv('OPENAI_MODEL','gpt-5.6-luna'),input=prompt); copy.update(_json(r.output_text))
    images=detail.get('productImageSet') or []; image=chosen.get('image') or detail.get('bigImage') or best.get('bigImage') or ''
    if image and image not in images: images=[image]+images
    return {'name':best.get('nameEn') or candidate['name'],'tagline':copy['tagline'],'description':copy['description'],'price':price,'compare_at':compare,'currency':'usd','image':image,'images':images[:6],'benefits':copy['benefits'],'supplier':'CJdropshipping','supplier_url':storefront_url(pid),'supplier_cost':cost,'cj_pid':pid,'cj_sku':best.get('sku') or detail.get('productSku'),'cj_vid':chosen['vid'],'cj_variant_name':chosen['name'],'variants':normalized,'variant_options':_build_option_schema(normalized),'cj_listed_num':best.get('listedNum',0),'source_note':'Product data, customer-selectable variant attributes and fulfillment identifiers imported from CJdropshipping API. Retail copy is affiliate-approved.'}
