import copy
import io
import json
import os
import tempfile
import threading
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from woo_sync.ai_providers import _llamacpp_endpoint
from woo_sync.content_proposals import review_fingerprint
from woo_sync.core import ValidationError, WooClient
from woo_sync.proposal_io import load_proposal
from woo_sync.review_service import Config, Handler, MAX_BODY, ReviewService, main
from test_sync import FakeApi


class DockerTransportTests(unittest.TestCase):
    def test_woo_internal_host_rejected_by_default(self):
        with self.assertRaises(ValidationError): WooClient('http://wordpress', 'key', 'secret')

    def test_woo_explicit_internal_host_uses_oauth_not_basic(self):
        client = WooClient('http://wordpress', 'key', 'secret', allowed_http_hosts=('wordpress',))
        response = io.BytesIO(b'[]')
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = response
            client.find('A-1')
            request = opener.return_value.open.call_args.args[0]
            self.assertTrue(request.get_header('Authorization').startswith('OAuth '))
            self.assertNotIn('secret', request.get_header('Authorization'))
            self.assertEqual(opener.call_args.args[0].proxies, {})

    def test_woo_allowlist_does_not_trust_other_hosts(self):
        for hosts in [(), ('wordpress',)]:
            for url in ['http://evil.example', 'http://wordpress.evil.example', 'http://sub.wordpress']:
                with self.subTest(url=url, hosts=hosts), self.assertRaises(ValidationError):
                    WooClient(url, 'key', 'secret', allowed_http_hosts=hosts)

    def test_woo_url_rejects_userinfo_query_fragment_control_and_bad_port(self):
        for url in ['http://u:p@wordpress','http://@wordpress','http://wordpress?','http://wordpress#',
                    'http://wordpress?token=demo','http://word\npress','http://wordpress:0','http://wordpress:99999',
                    'ftp://wordpress','http://wordpress/#x']:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                WooClient(url, 'key', 'secret', allowed_http_hosts=('wordpress',))

    def test_woo_loopback_and_https_preserved(self):
        for url in ['http://localhost:8090','http://127.0.0.1','http://[::1]','https://example.com']:
            self.assertIsInstance(WooClient(url, 'key', 'secret'), WooClient)

    def test_woo_allowlist_rejects_suffix_patterns_and_bare_string(self):
        for hosts in ['wordpress', ('*.internal',), ('evil.example',)]:
            with self.assertRaises(ValidationError): WooClient('http://wordpress','key','secret',allowed_http_hosts=hosts)

    def test_llama_docker_host_requires_exact_flag(self):
        for flag in ['', '0', 'true', 'yes', ' 1']:
            with patch.dict(os.environ, {'LLAMACPP_BASE_URL':'http://host.docker.internal:8080', 'LLAMACPP_ALLOW_DOCKER_HOST':flag}), self.assertRaises(ValidationError):
                _llamacpp_endpoint()

    def test_llama_exact_docker_host_enabled(self):
        with patch.dict(os.environ, {'LLAMACPP_BASE_URL':'http://host.docker.internal:8080', 'LLAMACPP_ALLOW_DOCKER_HOST':'1'}):
            self.assertEqual(_llamacpp_endpoint(), 'http://host.docker.internal:8080/v1/chat/completions')

    def test_llama_docker_flag_keeps_url_restrictions(self):
        for host in ['evil.example','sub.host.docker.internal','host.docker.internal.evil.test','other.internal',
                     'user@host.docker.internal','host.docker.internal/?x=1','host.docker.internal/v1']:
            with self.subTest(host=host), patch.dict(os.environ, {'LLAMACPP_BASE_URL':'http://'+host, 'LLAMACPP_ALLOW_DOCKER_HOST':'1'}), self.assertRaises(ValidationError):
                _llamacpp_endpoint()

    def test_llama_loopback_remains_available_in_docker_mode(self):
        with patch.dict(os.environ, {'LLAMACPP_BASE_URL':'http://localhost:8080','LLAMACPP_ALLOW_DOCKER_HOST':'1'}):
            self.assertIn('127.0.0.1:8080', _llamacpp_endpoint())


class ReviewServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'catalog.json'
        self.catalog = [dict(sku=sku, name='Fictional accessory', regular_price='20.00', stock_quantity=9,
                             status='publish', description='Fictional source description.',
                             short_description='Demo accessory.', image_alt='Demo image', image_id='7') for sku in ['A-1','B-2']]
        self.save_source()
        self.credentials = self.root/'private.json'
        self.credentials.write_text(json.dumps({'WC_CONSUMER_KEY':'private-consumer-key',
                                                'WC_CONSUMER_SECRET':'private-consumer-secret'}))
        self.config = Config('private-review-token', self.source, None, self.root/'state', self.credentials)
        self.service = ReviewService(self.config)
        self.api = FakeApi()
        self.api.stats = {'GET':0,'POST':0,'PUT':0}
        for n,row in enumerate(self.service.source_rows(), 1):
            self.api.products[row.sku] = dict(row.payload(), id=n, images=[{'id':7,'alt':'Demo image'}])
        self.client_patch = patch.object(self.service, 'client', return_value=self.api)
        self.client_patch.start(); self.addCleanup(self.client_patch.stop)

    def save_source(self):
        self.source.write_text(json.dumps(self.catalog), encoding='utf-8')

    def call(self, path, data=None, method='POST', token='private-review-token', raw=None, extra=None):
        headers=Message()
        if token is not None: headers['X-Lab-Token']=token
        body=raw if raw is not None else json.dumps(data or {}).encode()
        headers['Content-Type']='application/json'; headers['Content-Length']=str(len(body))
        if extra:
            for key,value in extra.items():
                if key in headers: del headers[key]
                if value is not None: headers[key]=value
        return self.service.dispatch(method,path,headers,io.BytesIO(body).read)

    def generate(self):
        status,result=self.call('/propose', {'sku':'a-1','provider':'demo'})
        self.assertEqual(status,200,result)
        return result

    def approve(self):
        self.generate()
        status,result=self.call('/review', {'sku':'A-1','decision':'approved'})
        self.assertEqual(status,200,result)
        return result

    def test_health_is_minimal_without_auth(self):
        self.assertEqual(self.call('/health',method='GET',token=None), (200,{'status':'ok','service':'ai-review'}))

    def test_missing_auth_rejected_on_every_protected_route(self):
        for path,method in [('/products','GET'),('/proposal?sku=A-1','GET'),('/propose','POST'),('/review','POST'),('/plan','POST'),('/apply','POST')]:
            with self.subTest(path=path): self.assertEqual(self.call(path,method=method,token=None)[0],401)

    def test_wrong_token_is_rejected(self):
        self.assertEqual(self.call('/products',method='GET',token='wrong')[0],401)

    def test_duplicate_auth_is_rejected(self):
        headers=Message();headers['X-Lab-Token']=self.config.token;headers['X-Lab-Token']=self.config.token
        self.assertEqual(self.service.dispatch('GET','/products',headers,lambda n:b'')[0],401)

    def test_missing_blank_token_blocks_startup(self):
        for value in ['', ' ', '\n\t']:
            with self.subTest(value=value), self.assertRaises(ValueError): Config(value)
        with patch.dict(os.environ,{},clear=True),patch('woo_sync.review_service.Server') as server:
            with patch('sys.stdout',new_callable=io.StringIO): self.assertEqual(main(),2)
            server.assert_not_called()

    def test_config_repr_hides_token_and_stock_policy_is_fixed(self):
        self.assertNotIn(self.config.token, repr(self.config))
        with patch.dict(os.environ, {'AI_REVIEW_TOKEN':'fixture-token','AI_REVIEW_STOCK_AUTHORITY':'source'}),self.assertRaises(ValueError): Config.from_env()

    def test_products_are_safe_and_do_not_require_credentials(self):
        self.credentials.unlink()
        status,result=self.call('/products',method='GET')
        self.assertEqual(status,200)
        self.assertEqual(len(result['products']),2)
        self.assertEqual(set(result['products'][0]), {'sku','name','description','short_description','image_alt'})

    def test_missing_unused_media_allowed(self):
        config=Config('fixture-token',self.source,self.root/'absent.json',self.root/'other-state',self.credentials)
        self.assertEqual(len(ReviewService(config).source_rows()),2)

    def test_required_missing_media_is_not_guessed(self):
        self.catalog[0]['asset']='keyboard';self.save_source()
        self.assertEqual(self.call('/products',method='GET')[0],409)

    def test_malformed_json_rejected(self):
        for raw in [b'{',b'[]',b'null',b'42',b'\xff',b'{"sku":"A-1","sku":"B-2"}',b'{"sku":NaN}']:
            with self.subTest(raw=raw): self.assertEqual(self.call('/propose',raw=raw)[0],400)

    def test_wrong_content_type_rejected(self):
        for value in [None,'text/plain','application/x-www-form-urlencoded']:
            self.assertEqual(self.call('/propose',extra={'Content-Type':value})[0],415)

    def test_oversized_body_rejected_without_reading(self):
        headers=Message();headers['X-Lab-Token']=self.config.token;headers['Content-Type']='application/json';headers['Content-Length']=str(MAX_BODY+1)
        def never_read(n): self.fail('Oversized body was read')
        self.assertEqual(self.service.dispatch('POST','/propose',headers,never_read)[0],413)

    def test_bad_length_chunked_and_truncated_body_rejected(self):
        for extra in [{'Content-Length':None},{'Content-Length':'-1'},{'Content-Length':'abc'},{'Content-Length':'10'},{'Transfer-Encoding':'chunked'}]:
            with self.subTest(extra=extra): self.assertEqual(self.call('/propose',raw=b'{}',extra=extra)[0],400)

    def test_invalid_sku_and_traversal_rejected(self):
        for sku in ['../x','/tmp/x','a/b','a\\b',' A-1','ą','a'*81,None,[],{}]:
            with self.subTest(sku=sku): self.assertEqual(self.call('/propose',{'sku':sku,'provider':'demo'})[0],400)

    def test_unknown_product(self):
        self.assertEqual(self.call('/propose',{'sku':'UNKNOWN','provider':'demo'})[0],404)

    def test_invalid_provider(self):
        for provider in ['other','DEMO',{},None]:
            self.assertEqual(self.call('/propose',{'sku':'A-1','provider':provider})[0],400)

    def test_invalid_decision(self):
        self.generate()
        for decision in ['pending','approve','APPROVED',None,[]]:
            self.assertEqual(self.call('/review',{'sku':'A-1','decision':decision})[0],400)

    def test_unknown_body_fields_and_arbitrary_urls_rejected(self):
        self.assertEqual(self.call('/propose',{'sku':'A-1','provider':'demo','url':'http://evil.example'})[0],400)
        self.assertEqual(self.call('/apply',{'sku':'A-1','apply':True})[0],400)

    def test_get_cannot_mutate_and_query_validation(self):
        for path in ['/apply?sku=A-1','/review?sku=A-1','/propose?sku=A-1']:
            self.assertEqual(self.call(path,method='GET')[0],404)
        for path in ['/proposal','/proposal?sku=A-1&sku=B-2','/products?url=x','/proposal?sku=A-1&path=x']:
            self.assertEqual(self.call(path,method='GET')[0],400)
        self.assertEqual(self.call('/apply?sku=A-1',{'sku':'A-1'})[0],400)
        self.assertEqual(self.call('/products',method='DELETE')[0],405)

    def test_missing_proposal_get_is_empty_but_mutations_fail(self):
        status,result=self.call('/proposal?sku=A-1',method='GET')
        self.assertEqual(status,200);self.assertFalse(result['exists'])
        for path in ['/plan','/apply','/review']:
            data={'sku':'A-1'}
            if path=='/review': data['decision']='approved'
            self.assertEqual(self.call(path,data)[0],404)

    def test_per_sku_proposal_case_insensitive_and_no_writes(self):
        result=self.generate()
        proposal=load_proposal(self.service.proposal_path('A-1'))
        self.assertEqual(len(proposal['items']),1)
        self.assertEqual(proposal['items'][0]['sku'],'A-1')
        self.assertEqual(result['approval'],'pending')
        self.assertEqual(self.api.writes,[])
        self.assertEqual(list(self.service.logs.iterdir()),[])

    def test_regenerate_resets_approval_atomically(self):
        old=self.approve()
        with patch('woo_sync.proposal_io.os.replace',wraps=os.replace) as replace:
            new=self.generate()
        self.assertTrue(replace.called)
        self.assertNotEqual(new['proposal_id'],old['proposal_id'])
        self.assertEqual(new['approval'],'pending')

    def test_failed_replace_preserves_original_file(self):
        self.approve();path=self.service.proposal_path('A-1');before=path.read_bytes()
        with patch('woo_sync.proposal_io.os.replace',side_effect=OSError('private-review-token')):
            self.assertEqual(self.call('/propose',{'sku':'A-1','provider':'demo'})[0],503)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(list(path.parent.glob('*.tmp')),[])

    def test_old_browser_proposal_id_cannot_approve_regenerated_content(self):
        old=self.generate();self.generate()
        self.assertEqual(self.call('/review',{'sku':'A-1','decision':'approved','proposal_id':old['proposal_id']})[0],409)

    def test_pending_cannot_plan(self):
        self.generate();self.assertEqual(self.call('/plan',{'sku':'A-1'})[0],409)

    def test_pending_cannot_apply(self):
        self.generate();self.assertEqual(self.call('/apply',{'sku':'A-1'})[0],409);self.assertEqual(self.api.writes,[])

    def test_rejected_cannot_plan_or_apply(self):
        self.generate();self.call('/review',{'sku':'A-1','decision':'rejected'})
        for path in ['/plan','/apply']: self.assertEqual(self.call(path,{'sku':'A-1'})[0],409)

    def test_approval_uses_existing_fingerprint(self):
        self.approve();p=load_proposal(self.service.proposal_path('A-1'));item=p['items'][0]
        self.assertEqual(item['review']['content_fingerprint'],review_fingerprint(p,item))
        self.assertEqual(self.api.writes,[])

    def test_stale_source_blocks_plan_and_apply(self):
        self.approve();self.catalog[0]['regular_price']='30.00';self.save_source()
        for path in ['/plan','/apply']: self.assertEqual(self.call(path,{'sku':'A-1'})[0],409)
        self.assertEqual(self.api.writes,[])

    def test_post_approval_content_mutation_blocks_apply(self):
        self.approve();path=self.service.proposal_path('A-1');p=json.loads(path.read_text())
        p['items'][0]['proposed']['description']='Edited after approval.';path.write_text(json.dumps(p))
        self.assertEqual(self.call('/apply',{'sku':'A-1'})[0],409)
        self.assertEqual(self.api.writes,[])

    def test_fake_approval_without_review_blocked(self):
        self.generate();path=self.service.proposal_path('A-1');p=json.loads(path.read_text())
        p['items'][0]['approval']='approved';path.write_text(json.dumps(p))
        self.assertEqual(self.call('/apply',{'sku':'A-1'})[0],409)

    def test_plan_calls_existing_full_source_engine_read_only(self):
        from woo_sync.core import sync
        self.approve()
        with patch('woo_sync.review_service.sync',wraps=sync) as engine:
            status,result=self.call('/plan',{'sku':'A-1'})
        self.assertEqual(status,200,result);self.assertEqual(result['mode'],'PLAN')
        self.assertEqual(len(engine.call_args.args[0]),2)
        self.assertIs(engine.call_args.args[2],False)
        self.assertEqual(engine.call_args.kwargs['stock_authority'],'woocommerce')
        self.assertEqual(self.api.writes,[])

    def test_apply_calls_existing_engine_and_second_run_skips(self):
        from woo_sync.core import sync
        self.approve();self.api.products['A-1']['stock_quantity']=4
        with patch('woo_sync.review_service.sync',wraps=sync) as engine:
            status,result=self.call('/apply',{'sku':'A-1'})
        self.assertEqual(status,200,result);self.assertEqual(result['mode'],'APPLIED')
        self.assertIs(engine.call_args.args[2],True)
        self.assertEqual(engine.call_args.kwargs['stock_authority'],'woocommerce')
        self.assertEqual(self.api.products['A-1']['stock_quantity'],4)
        writes=len(self.api.writes)
        status,result=self.call('/apply',{'sku':'A-1'})
        self.assertEqual(result['counts']['SKIP'],2);self.assertEqual(len(self.api.writes),writes)

    def test_other_product_preflight_failure_blocks_all_writes(self):
        self.approve();self.api.products['B-2']['type']='variable'
        status,result=self.call('/apply',{'sku':'A-1'})
        self.assertEqual(status,502,result);self.assertEqual(result['counts']['ERROR'],1)
        self.assertEqual(self.api.writes,[])
        self.assertEqual(result['operations'][0]['action'],'ERROR')

    def test_apply_rechecks_after_successful_plan(self):
        self.approve();self.assertEqual(self.call('/plan',{'sku':'A-1'})[0],200)
        self.catalog[0]['stock_quantity']=15;self.save_source()
        self.assertEqual(self.call('/apply',{'sku':'A-1'})[0],409);self.assertEqual(self.api.writes,[])

    def test_logs_are_unique_and_never_overwritten(self):
        self.approve();self.call('/plan',{'sku':'A-1'});files={p.name:p.read_bytes() for p in self.service.logs.iterdir()}
        self.call('/plan',{'sku':'A-1'})
        self.assertEqual(len(list(self.service.logs.iterdir())),2)
        for name,raw in files.items():self.assertEqual((self.service.logs/name).read_bytes(),raw)

    def test_service_errors_never_return_exception_or_secrets(self):
        with patch('woo_sync.review_service.get_provider',side_effect=RuntimeError('private-review-token private-consumer-secret traceback /run/secrets')):
            status,result=self.call('/propose',{'sku':'A-1','provider':'llamacpp'})
        self.assertEqual(status,502)
        raw=json.dumps(result)
        for secret in [self.config.token,'private-consumer-secret','traceback','/run/secrets']:self.assertNotIn(secret,raw)

    def test_response_redacts_unexpected_secret_strings(self):
        self.catalog[0]['description']='private-review-token private-consumer-secret private-consumer-key';self.save_source()
        status,result=self.call('/products',method='GET')
        self.assertEqual(status,200)
        for secret in ['private-review-token','private-consumer-secret','private-consumer-key']:self.assertNotIn(secret,json.dumps(result))

    def test_concurrent_generate_and_review_cannot_corrupt_state(self):
        self.generate();entered=threading.Event();release=threading.Event();results=[]
        def provider(row):
            entered.set();release.wait(5)
            return {'description':'Concurrent valid text.','short_description':'Demo.','image_alt':''}
        with patch('woo_sync.review_service.get_provider',return_value=provider):
            thread=threading.Thread(target=lambda:results.append(self.call('/propose',{'sku':'A-1','provider':'demo'})))
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                for path,data in [('/review',{'sku':'A-1','decision':'approved'}),('/plan',{'sku':'A-1'}),('/apply',{'sku':'A-1'})]:
                    self.assertEqual(self.call(path,data)[0],409)
            finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(results[0][0],200)
        self.assertEqual(load_proposal(self.service.proposal_path('A-1'))['items'][0]['approval'],'pending')
        self.assertEqual(self.api.writes,[])

    def test_real_http_handler_without_socket_or_network(self):
        class Connection:
            def __init__(self): self.output=bytearray()
            def makefile(self,*args): return io.BytesIO(b'GET /health HTTP/1.1\r\nHost: ai-review\r\n\r\n')
            def sendall(self,data): self.output.extend(data)
            def settimeout(self,n): pass
        connection=Connection()
        Handler(connection,('127.0.0.1',1234),SimpleNamespace(service=self.service))
        self.assertIn(b'200 OK',connection.output)
        self.assertIn(b'Cache-Control: no-store',connection.output)
        self.assertNotIn(b'Python',connection.output)
        self.assertNotIn(self.config.token.encode(),connection.output)

    def test_client_reads_private_key_file_and_overrides_saved_url(self):
        self.client_patch.stop()
        client=self.service.client()
        self.assertTrue(client.base.startswith('http://localhost:8090/'))
        self.assertTrue(client.transport_base.startswith('http://wordpress/'))
        self.assertEqual(client.secret,'private-consumer-secret')

    def test_missing_credentials_is_safe_service_error(self):
        self.approve();self.client_patch.stop();self.credentials.unlink()
        status,result=self.call('/plan',{'sku':'A-1'})
        self.assertEqual(status,503)
        self.assertNotIn(str(self.credentials),json.dumps(result))
