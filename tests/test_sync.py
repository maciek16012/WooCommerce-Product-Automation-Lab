import csv, io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from woo_sync.core import ApiError, ValidationError, WooClient, changes, desired_payload, diff_payload, load_csv, oauth_header, sync
from woo_sync.cli import main

class FakeApi:
    def __init__(self): self.products={}; self.writes=[]
    def find(self,sku): return self.products.get(sku)
    def categories(self): return {'peryferia':7,'kable':8}
    def create(self,payload):
        self.writes.append(('POST',payload))
        product={**payload,'id':len(self.products)+1};self.products[payload['sku']]=product;return product
    def update(self,product_id,payload):
        self.writes.append(('PUT',payload));product=next(p for p in self.products.values() if p['id']==product_id);product.update(payload);return product

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.csv=self.root/'products.csv'
        self.write([['A-1','Klawiatura','39.90','12','publish']]); self.serial=0
    def write(self,rows,header=None):
        with self.csv.open('w',encoding='utf-8',newline='') as f:
            w=csv.writer(f);w.writerow(header or ['sku','name','regular_price','stock_quantity','status']);w.writerows(rows)
    def run_sync(self,api,apply=True,stock_authority='source'):
        self.serial+=1
        with patch('sys.stdout',new_callable=io.StringIO):
            return sync(
                load_csv(self.csv),
                api,
                apply,
                self.root/f'{self.serial}.jsonl',
                stock_authority=stock_authority,
            )
    def test_create_skip_update_plan(self):
        api=FakeApi();self.assertEqual(self.run_sync(api,False)['CREATE'],1);self.assertEqual(api.writes,[])
        self.assertEqual(self.run_sync(api)['CREATE'],1);self.assertEqual(self.run_sync(api)['SKIP'],1);self.assertEqual(len(api.writes),1)
        self.write([['A-1','Klawiatura','49.90','8','publish']]);self.assertEqual(self.run_sync(api)['UPDATE'],1)
        self.assertEqual(api.writes[-1],('PUT',{'regular_price':'49.90','stock_quantity':8}))
    def test_duplicate_case_insensitive_blocks_entire_file(self):
        self.write([['A-1','A','1','1','publish'],['a-1','B','1','1','publish']])
        with self.assertRaisesRegex(ValidationError,'powtórzone SKU'):load_csv(self.csv)
    def test_invalid_values(self):
        for price,stock in [('NaN','1'),('Infinity','1'),('-1','1'),('1e2','1'),('1.001','1'),('2','-1'),('2','1.5')]:
            with self.subTest(price=price,stock=stock):
                self.write([['A','Name',price,stock,'publish']])
                with self.assertRaises(ValidationError):load_csv(self.csv)
    def test_duplicate_header(self):
        self.write([],['sku','name','regular_price','stock_quantity','status','sku'])
        with self.assertRaises(ValidationError):load_csv(self.csv)
    def test_validation_precedes_network_and_logs_error(self):
        self.write([['A','Name','1','1','publish'],['B','Name','NaN','1','publish']])
        log=self.root/'bad.jsonl'
        with patch('woo_sync.cli.WooClient') as client,patch('sys.stderr',new_callable=io.StringIO):
            self.assertEqual(main(['sync',str(self.csv),'--apply','--log',str(log)]),2);client.assert_not_called()
        self.assertEqual(json.loads(log.read_text())['writes'],0)
    def test_preflight_error_blocks_prior_valid_create(self):
        self.write([['A','A','1','1','publish'],['B','B','1','1','publish']]);api=FakeApi();api.products['B']={'id':8,'sku':'B','type':'variable'}
        self.assertEqual(self.run_sync(api)['ERROR'],1);self.assertEqual(api.writes,[])
    def test_api_write_failure_preserves_other_rows(self):
        self.write([['A','A','1','1','publish'],['B','B','1','1','publish']]);api=FakeApi();original=api.create
        def create(p):
            if p['sku']=='A':raise ApiError('HTTP 500')
            return original(p)
        api.create=create
        self.assertEqual(self.run_sync(api),dict(CREATE=1,UPDATE=0,SKIP=0,ERROR=1));self.assertIn('B',api.products)
    def test_unknown_category_preflight(self):
        self.write([['A','A','1','1','publish','typo']],['sku','name','regular_price','stock_quantity','status','categories'])
        api=FakeApi();self.assertEqual(self.run_sync(api)['ERROR'],1);self.assertEqual(api.writes,[])
    def test_categories_description_and_alt_idempotence(self):
        self.write([['A','A','1','1','publish','peryferia|kable','A & B','9','ALT']],['sku','name','regular_price','stock_quantity','status','categories','description','image_id','image_alt'])
        row=load_csv(self.csv)[0];p=desired_payload(row,None,{'peryferia':7,'kable':8})
        current={**p,'description':'<p>A &amp; B</p>\n','categories':[{'id':8,'name':'B'},{'id':7,'name':'A'}],'images':[{'id':9,'src':'https://example.test/image.png','alt':'ALT'}]}
        self.assertEqual(diff_payload(desired_payload(row,current,{'peryferia':7,'kable':8}),current),{})
        current['images'][0]['alt']='OLD';self.assertEqual(diff_payload(desired_payload(row,current,{'peryferia':7,'kable':8}),current),{'images':[{'id':9,'alt':'ALT'}]})
    def test_image_source_metadata_prevents_reupload(self):
        self.write([['A','A','1','1','publish','https://example.test/original.png','ALT']],['sku','name','regular_price','stock_quantity','status','image_url','image_alt'])
        row=load_csv(self.csv)[0];current={**row.payload(),'images':[{'id':10,'src':'https://store.test/uploads/original-1.png','alt':'ALT'}],'meta_data':[{'id':1,'key':'_lab_image_source','value':'https://example.test/original.png'}]}
        self.assertEqual(diff_payload(desired_payload(row,current,{}),current),{})
    def test_missing_optional_columns_preserve_fields(self):
        row=load_csv(self.csv)[0];current={**row.payload(),'description':'Keep','images':[{'id':20,'alt':'Keep'}],'categories':[{'id':3}]}
        self.assertEqual(changes(row,current),{})
    def test_woocommerce_stock_authority_preserves_existing_stock(self):
        api=FakeApi()
        row=load_csv(self.csv)[0]
        api.products['A-1']={
            **row.payload(),
            'id':7,
            'stock_quantity':3,
        }

        counts=self.run_sync(
            api,
            stock_authority='woocommerce',
        )

        self.assertEqual(counts['SKIP'],1)
        self.assertEqual(api.writes,[])
        self.assertEqual(
            api.products['A-1']['stock_quantity'],
            3,
        )

    def test_woocommerce_stock_authority_sets_stock_on_create(self):
        api=FakeApi()

        counts=self.run_sync(
            api,
            stock_authority='woocommerce',
        )

        self.assertEqual(counts['CREATE'],1)
        self.assertEqual(
            api.writes[0][1]['stock_quantity'],
            12,
        )
    def test_http_restricted_to_loopback(self):
        for url in ['http://example.com','http://192.168.1.2','https://user:pass@example.com','https://example.com/?secret=1']:
            with self.assertRaises(ValidationError):WooClient(url,'key','secret')
        WooClient('http://localhost:8090','key','secret');WooClient('https://example.com','key','secret')
    def test_oauth_header_hides_secret_and_changes_nonce(self):
        a=oauth_header('GET','http://localhost:8090/wp-json/wc/v3/products?sku=A-1','test-key','test-secret',1,'nonce')
        self.assertTrue(a.startswith('OAuth '));self.assertNotIn('test-secret',a);self.assertNotIn('Basic',a)
        self.assertNotEqual(a,oauth_header('GET','http://localhost:8090/wp-json/wc/v3/products?sku=A-2','test-key','test-secret',1,'nonce'))
    def test_write_not_retried_and_error_body_not_logged(self):
        import urllib.error
        error=urllib.error.HTTPError('http://localhost',500,'server',{},io.BytesIO(b'{"message":"test-secret"}'))
        with patch('urllib.request.OpenerDirector.open',side_effect=error) as request:
            with self.assertRaises(ApiError) as caught:WooClient('http://localhost:8090','key','test-secret').create({'sku':'A'})
            self.assertEqual(request.call_count,1);self.assertNotIn('test-secret',str(caught.exception))
    def test_redirects_denied(self):
        self.assertIsNone(WooClient._NoRedirect().redirect_request(None,None,302,'',{},'https://other.test'))
    def test_existing_log_not_overwritten(self):
        log=self.root/'existing.jsonl';log.write_text('keep')
        with self.assertRaises(FileExistsError):sync(load_csv(self.csv),FakeApi(),True,log)
        self.assertEqual(log.read_text(),'keep')

if __name__=='__main__':unittest.main()
