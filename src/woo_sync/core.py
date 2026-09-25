"""CSV validation, OAuth transport and plan-first product synchronization."""
from __future__ import annotations
import base64, csv, hashlib, hmac, html, ipaddress, json, re, secrets, time
import urllib.error
import urllib.parse as urlparse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS = ('sku','name','regular_price','stock_quantity','status')
OPTIONAL = ('description','short_description','categories','image_id','image_url','image_alt')
class ValidationError(ValueError): pass
class ApiError(RuntimeError): pass

def local_host(host):
    if host == 'localhost': return True
    try: return ipaddress.ip_address(host).is_loopback
    except ValueError: return False

def safe_url(value):
    p = urlparse.urlsplit(value)
    if (not p.hostname or p.username or p.password or p.query or p.fragment or p.scheme not in ('http','https')
        or (p.scheme=='http' and not local_host(p.hostname))):
        raise ValidationError('URL: HTTPS wymagane poza loopback; bez loginu, query i fragmentu')
    return p

@dataclass(frozen=True)
class ProductRow:
    line: int
    sku: str
    name: str
    regular_price: str
    stock_quantity: int
    status: str
    extra: dict
    def payload(self):
        return dict(type='simple',sku=self.sku,name=self.name,regular_price=self.regular_price,
                    manage_stock=True,stock_quantity=self.stock_quantity,status=self.status,
                    **{k:v for k,v in self.extra.items() if k in ('description','short_description')})

def load_records(records, fieldnames=None):
    """Validate normalized mapping records and return ProductRow objects."""
    records = list(records)

    if fieldnames is None:
        names = []
        for _, data in records:
            if not isinstance(data, dict):
                raise ValidationError('Rekord produktu musi być obiektem')
            for key in data:
                if key not in names:
                    names.append(key)
    else:
        names = list(fieldnames)

    if (
        not set(FIELDS).issubset(names)
        or set(names) - set(FIELDS + OPTIONAL)
        or len(names) != len(set(names))
    ):
        raise ValidationError('Nieprawidłowe lub powtórzone nagłówki danych')

    problems = []
    rows = []
    seen = set()

    for line, raw in records:
        try:
            if not isinstance(raw, dict):
                raise ValidationError('rekord produktu musi być obiektem')

            if None in raw:
                raise ValidationError('liczba kolumn')

            if any(key not in raw for key in FIELDS):
                raise ValidationError('brak wymaganych pól')

            original_keys = set(raw)

            data = {
                key: (
                    ''
                    if raw.get(key) is None
                    else str(raw.get(key)).strip()
                )
                for key in names
            }

            sku = data['sku']

            if not re.fullmatch(
                r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}',
                sku,
            ):
                raise ValidationError(
                    'SKU: litery ASCII, cyfry, . _ -, maks. 80'
                )

            if sku.casefold() in seen:
                raise ValidationError(
                    'powtórzone SKU (także różna wielkość liter)'
                )

            seen.add(sku.casefold())

            if not data['name'] or len(data['name']) > 200:
                raise ValidationError(
                    'nazwa wymagana, maks. 200 znaków'
                )

            if not re.fullmatch(
                r'\d{1,8}(\.\d{1,2})?',
                data['regular_price'],
            ):
                raise ValidationError(
                    'cena nieujemna, maks. 2 miejsca po kropce'
                )

            if not re.fullmatch(
                r'\d{1,7}',
                data['stock_quantity'],
            ):
                raise ValidationError(
                    'stan: liczba całkowita 0–9999999'
                )

            if data['status'] not in {
                'draft',
                'publish',
                'pending',
                'private',
            }:
                raise ValidationError('nieznany status')

            extra = {
                key: data[key]
                for key in OPTIONAL
                if key in original_keys
            }

            for field in ('description', 'short_description'):
                value = extra.get(field, '')
                if (
                    len(value) > 30000
                    or '<' in value
                    or '>' in value
                ):
                    raise ValidationError(
                        'opisy: zwykły tekst bez HTML, maks. 30000'
                    )

            if 'categories' in extra:
                cats = [
                    category.strip()
                    for category
                    in extra['categories'].split('|')
                ]

                if (
                    not all(
                        re.fullmatch(
                            r'[a-z0-9]+(?:-[a-z0-9]+)*',
                            category,
                        )
                        for category in cats
                    )
                    or len(cats) != len(set(cats))
                ):
                    raise ValidationError(
                        'kategorie: unikalne slugi rozdzielone |'
                    )

                extra['categories'] = cats

            if (
                extra.get('image_id')
                and not re.fullmatch(
                    r'[1-9]\d*',
                    extra['image_id'],
                )
            ):
                raise ValidationError(
                    'image_id: dodatnia liczba całkowita'
                )

            if (
                extra.get('image_id')
                and extra.get('image_url')
            ):
                raise ValidationError(
                    'wybierz image_id albo image_url'
                )

            if extra.get('image_url'):
                safe_url(extra['image_url'])

            if (
                extra.get('image_id')
                or extra.get('image_url')
            ) and not extra.get('image_alt'):
                raise ValidationError('obraz wymaga ALT')

            if len(extra.get('image_alt', '')) > 500:
                raise ValidationError(
                    'ALT: maks. 500 znaków'
                )

            rows.append(
                ProductRow(
                    line,
                    sku,
                    data['name'],
                    f"{Decimal(data['regular_price']):.2f}",
                    int(data['stock_quantity']),
                    data['status'],
                    extra,
                )
            )

        except ValidationError as exc:
            problems.append(f'Wiersz {line}: {exc}')

    if problems:
        raise ValidationError('\n'.join(problems))

    if not rows:
        raise ValidationError('Źródło nie zawiera produktów')

    return rows


def load_csv(path):
    """Load UTF-8 CSV and validate it through the shared record pipeline."""
    try:
        with Path(path).open(
            encoding='utf-8-sig',
            newline='',
        ) as stream:
            reader = csv.DictReader(stream, strict=True)
            names = reader.fieldnames or []
            records = [
                (reader.line_num, data)
                for data in reader
            ]

    except (UnicodeError, csv.Error) as exc:
        raise ValidationError(
            'Nieprawidłowy CSV UTF-8'
        ) from exc

    return load_records(records, names)

def oauth_header(method,url,key,secret,timestamp=None,nonce=None):
    quote=lambda s:urlparse.quote(str(s),safe='~')
    p=urlparse.urlsplit(url)
    params=dict(urlparse.parse_qsl(p.query))
    oauth=dict(oauth_consumer_key=key,oauth_nonce=nonce or secrets.token_hex(16),oauth_timestamp=str(timestamp or int(time.time())),oauth_signature_method='HMAC-SHA256')
    params.update(oauth)
    normalized='&'.join(f'{quote(k)}={quote(v)}' for k,v in sorted(params.items()))
    base='&'.join([method.upper(),quote(urlparse.urlunsplit((p.scheme,p.netloc,p.path,'',''))),quote(normalized)])
    oauth['oauth_signature']=base64.b64encode(hmac.new((quote(secret)+'&').encode(),base.encode(),hashlib.sha256).digest()).decode()
    return 'OAuth '+', '.join(f'{quote(k)}="{quote(v)}"' for k,v in sorted(oauth.items()))

class WooClient:
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl): return None
    def __init__(self,url,key,secret,timeout=20):
        self.parsed=safe_url(url)
        if not key or not secret: raise ValidationError('Brak lokalnych kluczy API')
        self.base=url.rstrip('/')+'/wp-json/wc/v3/'
        self.key,self.secret,self.timeout=key,secret,timeout
        self.stats=dict(GET=0,POST=0,PUT=0)
    def request(self,method,path,payload=None):
        url=self.base+path
        data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None
        attempts=3 if method=='GET' else 1
        for attempt in range(attempts):
            auth=(oauth_header(method,url,self.key,self.secret) if self.parsed.scheme=='http' else 'Basic '+base64.b64encode(f'{self.key}:{self.secret}'.encode()).decode())
            req=urllib.request.Request(url,data=data,method=method,headers={'Authorization':auth,'Accept':'application/json','Content-Type':'application/json','User-Agent':'WooCommerceProductAutomationLab/1.0'})
            self.stats[method]=self.stats.get(method,0)+1
            try:
                with urllib.request.build_opener(self._NoRedirect).open(req,timeout=self.timeout) as response: return json.load(response)
            except urllib.error.HTTPError as exc:
                if method=='GET' and exc.code in (429,502,503,504) and attempt+1<attempts:
                    time.sleep(2**attempt); continue
                raise ApiError(f'HTTP {exc.code} przy {method}; brak automatycznego ponawiania zapisu') from None
            except (urllib.error.URLError,TimeoutError,OSError):
                if method=='GET' and attempt+1<attempts:
                    time.sleep(2**attempt); continue
                raise ApiError(f'Błąd sieci przy {method}; stan zapisu niepewny, ponów plan po SKU') from None
            except (ValueError,TypeError): raise ApiError('Nieprawidłowa odpowiedź JSON API') from None
    def find(self,sku):
        results=self.request('GET','products?'+urlparse.urlencode({'sku':sku,'per_page':100,'context':'edit'}))
        if not isinstance(results,list): raise ApiError('Nieoczekiwany format wyszukiwania SKU')
        exact=[p for p in results if str(p.get('sku','')).casefold()==sku.casefold()]
        if len(exact)>1: raise ApiError('Niejednoznaczne SKU')
        if exact and exact[0]['sku']!=sku: raise ApiError('Konflikt wielkości liter SKU')
        return exact[0] if exact else None
    def categories(self):
        result,page={},1
        while True:
            batch=self.request('GET',f'products/categories?per_page=100&page={page}&hide_empty=false')
            if not isinstance(batch,list): raise ApiError('Nieprawidłowa lista kategorii')
            result.update({c['slug']:c['id'] for c in batch})
            if len(batch)<100: return result
            page+=1
    def create(self,payload): return self.request('POST','products',payload)
    def update(self,product_id,payload): return self.request('PUT',f'products/{product_id}',payload)

def normalized_text(value): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',str(value or '')))).strip()

def desired_payload(row,current,categories):
    desired=row.payload()
    if 'categories' in row.extra: desired['categories']=[{'id':categories[s]} for s in row.extra['categories']]
    image_id,src=row.extra.get('image_id'),row.extra.get('image_url')
    if image_id or src:
        images=(current or {}).get('images',[])
        first=images[0] if images else {}
        source=next((m.get('value') for m in (current or {}).get('meta_data',[]) if m.get('key')=='_lab_image_source'),None)
        if image_id: image={'id':int(image_id)}
        elif first and (first.get('src')==src or source==src): image={'id':first['id']}
        else: image={'src':src}
        image['alt']=row.extra['image_alt']
        desired['images']=[image]+[{'id':i['id'],'alt':i.get('alt','')} for i in images[1:]]
        if src: desired['meta_data']=[{'key':'_lab_image_source','value':src}]
        elif source: desired['meta_data']=[{'key':'_lab_image_source','value':''}]
    elif row.extra.get('image_alt'):
        if not current or not current.get('images'): raise ApiError('ALT bez istniejącego obrazu')
        desired['images']=[{'id':i['id'],'alt':row.extra['image_alt'] if n==0 else i.get('alt','')} for n,i in enumerate(current['images'])]
    return desired

def diff_payload(desired,current):
    if current.get('type')!='simple': raise ApiError('SKU należy do produktu innego typu niż simple')
    delta={}
    for k,v in desired.items():
        old=current.get(k)
        if k=='regular_price':
            try: same=Decimal(str(old))==Decimal(v)
            except InvalidOperation: same=False
        elif k in ('name','description','short_description'): same=normalized_text(old)==normalized_text(v)
        elif k=='categories': same={c['id'] for c in old or []}=={c['id'] for c in v}
        elif k=='images': same=[{'id':i['id'],'alt':i.get('alt','')} for i in old or []]==v
        elif k=='meta_data': same=all(any(m.get('key')==x['key'] and m.get('value')==x['value'] for m in old or []) for x in v)
        else: same=old==v
        if not same: delta[k]=v
    return delta

def changes(row,current): return diff_payload(row.payload(),current)

def sync(rows,api,apply,log_path):
    counts=dict(CREATE=0,UPDATE=0,SKIP=0,ERROR=0)
    log_path.parent.mkdir(parents=True,exist_ok=True)
    with log_path.open('x',encoding='utf-8') as out:
        def emit(record):
            out.write(json.dumps(record,ensure_ascii=False)+'\n'); out.flush()
        plan=[]
        try:
            cats=api.categories() if any('categories' in r.extra for r in rows) else {}
            missing=sorted({s for r in rows for s in r.extra.get('categories',[]) if s not in cats})
            if missing: raise ApiError('Nieznane kategorie: '+', '.join(missing))
            for row in rows:
                current=api.find(row.sku)
                desired=desired_payload(row,current,cats)
                payload=diff_payload(desired,current) if current else desired
                action=('UPDATE' if payload else 'SKIP') if current else 'CREATE'
                plan.append((row,current,payload,action))
        except ApiError as exc:
            emit(dict(action='ERROR',phase='PREFLIGHT',error=str(exc),writes=0))
            counts['ERROR']+=1
            print(f'ERROR PREFLIGHT: {exc}')
            return counts
        for row,current,payload,action in plan:
            record=dict(line=row.line,sku=row.sku,action=action,mode='APPLIED' if apply else 'PLAN',product_id=current['id'] if current else None,
                changes={k:{'before':current.get(k) if current else None,'after':v} for k,v in payload.items()})
            try:
                if apply and action!='SKIP':
                    result=api.update(current['id'],payload) if current else api.create(payload)
                    record['product_id']=result['id']
            except (ApiError,KeyError,TypeError) as exc:
                record.update(action='ERROR',error=str(exc) if isinstance(exc,ApiError) else 'Nieprawidłowa odpowiedź zapisu')
            counts[record['action']]+=1
            emit(record)
            print(f"{record['action']:6} {row.sku} "+json.dumps(record['changes'],ensure_ascii=False))
        emit(dict(event='SUMMARY',counts=counts,requests=getattr(api,'stats',{})))
    return counts
