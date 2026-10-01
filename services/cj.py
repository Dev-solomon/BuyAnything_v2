import os, requests
from urllib.parse import quote_plus

BASE=os.getenv('CJ_API_BASE','https://developers.cjdropshipping.com/api2.0/v1').rstrip('/')

class CJError(RuntimeError): pass

def _token():
    token=os.getenv('CJ_ACCESS_TOKEN','').strip()
    if not token: raise CJError('CJ_ACCESS_TOKEN is missing. Add it to .env.')
    return token

def _request(method,path,**kwargs):
    headers=kwargs.pop('headers',{})
    headers['CJ-Access-Token']=_token(); headers.setdefault('Content-Type','application/json')
    r=requests.request(method,BASE+path,headers=headers,timeout=30,**kwargs)
    try: body=r.json()
    except Exception: raise CJError(f'CJ returned HTTP {r.status_code}: {r.text[:250]}')
    if not r.ok or body.get('result') is False or body.get('success') is False:
        raise CJError(body.get('message') or f'CJ API error {r.status_code}')
    return body.get('data')

def test_connection(): return _request('GET','/setting/get')

def search_products(keyword,size=8):
    data=_request('GET','/product/listV2',params={'page':1,'size':size,'keyWord':keyword,'orderBy':1,'sort':'desc','features':'enable_description'}) or {}
    out=[]
    for group in data.get('content',[]): out.extend(group.get('productList',[]))
    return out

def product_detail(pid): return _request('GET','/product/query',params={'pid':pid,'features':'enable_video'}) or {}
def variants(pid): return _request('GET','/product/variant/query',params={'pid':pid}) or []

def storefront_url(pid): return f'https://cjdropshipping.com/product/{quote_plus(str(pid))}.html'

def create_order(order_number, shipping, vid, quantity=1, logistic_name=None):
    # Stripe has already charged the shopper. CJ payType=2 uses your CJ balance for supplier fulfillment.
    logistic_name=logistic_name or os.getenv('CJ_LOGISTIC_NAME','CJPacket Ordinary')
    payload={
      'orderNumber':order_number,'shippingZip':shipping.get('postal_code',''),
      'shippingCountry':shipping.get('country_name') or shipping.get('country',''),
      'shippingCountryCode':shipping.get('country',''),'shippingProvince':shipping.get('state',''),
      'shippingCity':shipping.get('city',''),'shippingPhone':shipping.get('phone',''),
      'shippingCustomerName':shipping.get('name',''),'shippingAddress':shipping.get('line1',''),
      'shippingAddress2':shipping.get('line2',''),'email':shipping.get('email',''),
      'payType':int(os.getenv('CJ_PAY_TYPE','2')),'logisticName':logistic_name,
      'fromCountryCode':os.getenv('CJ_FROM_COUNTRY','CN'),'platform':'shopify',
      'products':[{'vid':vid,'quantity':int(quantity),'storeLineItemId':order_number+'-1'}]
    }
    return _request('POST','/shopping/order/createOrderV2',json=payload) or {}
