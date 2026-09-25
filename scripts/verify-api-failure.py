"""Fault-injection using a real rejected WooCommerce image update."""
import csv,io,json
from contextlib import redirect_stdout
from pathlib import Path
from woo_sync.core import WooClient,load_csv,sync
root=Path(__file__).resolve().parents[1];c=json.loads((root/'.secrets/woocommerce.json').read_text());api=WooClient(*[c[k] for k in ('WC_URL','WC_CONSUMER_KEY','WC_CONSUMER_SECRET')])
rows=list(csv.DictReader((root/'data/products.csv').open(encoding='utf-8')))
before={r['sku']:api.find(r['sku']) for r in rows}
rows[0]['image_id']='999999999'
p=root/'logs/invalid-image.csv'
with p.open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
api.stats=dict(GET=0,POST=0,PUT=0)
with redirect_stdout(io.StringIO()):result=sync(load_csv(p),api,True,root/'logs/11-api-write-error.jsonl')
assert result==dict(CREATE=0,UPDATE=0,SKIP=5,ERROR=1),result
for sku,old in before.items():
    after=api.find(sku)
    for field in ('id','name','regular_price','stock_quantity','description','images','categories'):assert old[field]==after[field],(sku,field)
print('Real rejected PUT: ERROR 1 / SKIP 5; all product data preserved')
