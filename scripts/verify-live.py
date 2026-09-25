"""Real API verification: update, invalid CSV, invalid credentials, preserve records."""
import csv,io,json
from pathlib import Path
from contextlib import redirect_stdout,redirect_stderr
from woo_sync.core import WooClient,load_csv,sync
from woo_sync.cli import main
root=Path(__file__).resolve().parents[1]
creds=json.loads((root/'.secrets/woocommerce.json').read_text())
api=WooClient(*[creds[k] for k in ('WC_URL','WC_CONSUMER_KEY','WC_CONSUMER_SECRET')])
rows=list(csv.DictReader((root/'data/products.csv').open(encoding='utf-8')))
rows[0]['regular_price']='179.00';rows[0]['stock_quantity']='21'
with (root/'data/products.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
with redirect_stdout(io.StringIO()):
    result=sync(load_csv(root/'data/products.csv'),api,False,root/'logs/06-update-plan.jsonl')
assert result==dict(CREATE=0,UPDATE=1,SKIP=5,ERROR=0),result
api.stats=dict(GET=0,POST=0,PUT=0)
with redirect_stdout(io.StringIO()): result=sync(load_csv(root/'data/products.csv'),api,True,root/'logs/07-update.jsonl')
assert result==dict(CREATE=0,UPDATE=1,SKIP=5,ERROR=0),result
assert api.stats['PUT']==1 and api.stats['POST']==0
records=[json.loads(x) for x in (root/'logs/07-update.jsonl').read_text(encoding='utf-8').splitlines()]
assert set(records[0]['changes'])=={'regular_price','stock_quantity'}
product=api.find('BL-KEY-01');assert product['regular_price']=='179.00' and product['stock_quantity']==21
print('UPDATE verified: 1 PUT, only price and stock; 5 SKIP')
with redirect_stdout(io.StringIO()): result=sync(load_csv(root/'data/products.csv'),api,True,root/'logs/08-skip-after-update.jsonl')
assert result['SKIP']==6 and result['ERROR']==0
before={r['sku']:api.find(r['sku']) for r in rows}
invalid=root/'logs/invalid.csv'
invalid.write_text('sku,name,regular_price,stock_quantity,status\nBL-KEY-01,SHOULD NOT WRITE,1,1,publish\nBAD,Invalid,NaN,-2,publish\n',encoding='utf-8')
with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()): code=main(['sync',str(invalid),'--apply','--log',str(root/'logs/09-invalid-csv.jsonl')])
assert code==2
bad=WooClient(creds['WC_URL'],creds['WC_CONSUMER_KEY'],'intentionally-invalid-test-secret')
with redirect_stdout(io.StringIO()): result=sync(load_csv(root/'data/products.csv'),bad,True,root/'logs/10-api-401.jsonl')
assert result['ERROR']==1 and bad.stats['POST']==bad.stats['PUT']==0
for sku,p in before.items():
    after=api.find(sku)
    for field in ('id','name','regular_price','stock_quantity','description','images','categories'): assert after[field]==p[field],(sku,field)
print('Invalid CSV and real HTTP 401: zero writes; all 6 products unchanged')
summary={'updated_product_id':product['id'],'updated_product_url':product['permalink'],'update_fields':['regular_price','stock_quantity'],'new_price':'179.00','new_stock':21,'invalid_csv_exit':code,'api_failure':'HTTP 401','products_preserved':6}
(root/'docs/api-test-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
