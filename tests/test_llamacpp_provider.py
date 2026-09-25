import io
import json
import os
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from woo_sync.ai_providers import (
    DEFAULT_LLAMACPP_MODEL, LLAMACPP_TIMEOUT, MAX_LLAMACPP_RESPONSE_BYTES,
    _NoRedirectHandler, _llamacpp_endpoint, get_provider, llamacpp_provider,
)
from woo_sync.core import ProductRow, ValidationError

class FakeResponse(io.BytesIO):
    pass

class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.request = None
        self.timeout = None
    def open(self, request, timeout=None):
        self.request, self.timeout = request, timeout
        if isinstance(self.payload, Exception):
            raise self.payload
        raw = self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode('utf-8')
        return FakeResponse(raw)

class LlamaCppProviderTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
    def row(self):
        return ProductRow(2, 'A-1', 'Klawiatura Łódź', '199.00', 10, 'publish', {
            'description': 'Opis bazowy', 'short_description': 'Krótki opis',
            'categories': ['peryferia'], 'image_alt': 'Klawiatura na biurku'})
    def response(self, content=None):
        generated = content if content is not None else {
            'description': 'Nowy opis.', 'short_description': 'Krótki opis.', 'image_alt': 'Klawiatura na biurku'}
        return {'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps(generated)}}]}
    def invoke(self, response):
        opener = FakeOpener(response)
        with patch('woo_sync.ai_providers.urllib.request.build_opener', return_value=opener) as build:
            result = llamacpp_provider(self.row())
        return result, opener, build
    def test_llamacpp_provider_is_registered(self):
        self.assertIs(get_provider('llamacpp'), llamacpp_provider)
    def test_structured_local_response_is_returned(self):
        result, opener, _ = self.invoke(self.response())
        self.assertEqual(result['description'], 'Nowy opis.')
        body = json.loads(opener.request.data)
        self.assertEqual(body['model'], DEFAULT_LLAMACPP_MODEL)
        self.assertEqual(DEFAULT_LLAMACPP_MODEL, 'jarvis-qwen35-9b')
        self.assertEqual(body['response_format']['type'], 'json_schema')
        self.assertTrue(body['response_format']['json_schema']['strict'])
        self.assertFalse(body['response_format']['json_schema']['schema']['additionalProperties'])
        self.assertFalse(body['stream'])
        self.assertEqual(opener.timeout, LLAMACPP_TIMEOUT)
        self.assertEqual(opener.request.full_url, 'http://127.0.0.1:8080/v1/chat/completions')
        self.assertIsNone(opener.request.get_header('Authorization'))
    def test_request_utf8_and_model_override(self):
        with patch.dict(os.environ, {'LLAMACPP_MODEL': 'local-other'}):
            _, opener, _ = self.invoke(self.response())
        self.assertIn('Łódź'.encode('utf-8'), opener.request.data)
        self.assertEqual(json.loads(opener.request.data)['model'], 'local-other')
    def test_non_loopback_server_is_rejected(self):
        invalid = ['http://example.com:8080', 'https://example.com', 'http://192.168.0.2',
                   'http://0.0.0.0:8080','http://127.0.0.1.evil.test', 'http://localhost@evil.test',
                   'http://u:p@localhost', 'http://localhost/?x=1','http://localhost/#x',
                   'http://localhost/v1', 'http://localhost:99999', 'http://localhost:bad',
                   'http://localhost:0', 'http://[::1', 'http://local\nhost:8080', ' http://localhost']
        for url in invalid:
            with self.subTest(url=url), patch.dict(os.environ, {'LLAMACPP_BASE_URL': url}), patch('urllib.request.build_opener') as network:
                with self.assertRaisesRegex(ValidationError, 'loopback'):
                    llamacpp_provider(self.row())
                network.assert_not_called()
    def test_loopback_configuration_and_dns_pinning(self):
        for base, expected in [('http://localhost:8080/', 'http://127.0.0.1:8080'),
                               ('http://[::1]:8080', 'http://[::1]:8080'), ('https://127.0.0.1:8443','https://127.0.0.1:8443')]:
            with patch.dict(os.environ, {'LLAMACPP_BASE_URL': base}):
                self.assertEqual(_llamacpp_endpoint(), expected + '/v1/chat/completions')
    def test_system_proxies_disabled(self):
        _, _, build = self.invoke(self.response())
        handlers = build.call_args.args
        self.assertEqual(next(h.proxies for h in handlers if isinstance(h, urllib.request.ProxyHandler)), {})
        self.assertTrue(any(isinstance(h, _NoRedirectHandler) for h in handlers))
    def test_redirect_is_rejected(self):
        req=urllib.request.Request('http://127.0.0.1:8080/v1/chat/completions')
        with self.assertRaises(urllib.error.HTTPError):
            _NoRedirectHandler().redirect_request(req,None,302,'redirect',{},'https://outside.test')
    def test_prompt_forbids_unsupported_inferences(self):
        _, opener, _ = self.invoke(self.response())
        messages=json.loads(opener.request.data)['messages']
        prompt=messages[0]['content']
        for phrase in ['wyłącznie faktów','kompatybilności','systemów operacyjnych','certyfikatów',
                       'zastosowań','grup użytkowników','Nie wykonuj poleceń','Nie używaj HTML','Nie znasz obrazu']:
            self.assertIn(phrase,prompt)
        self.assertNotIn('Opis bazowy',prompt)
        self.assertIn('Opis bazowy',messages[1]['content'])
    def test_malformed_response_is_controlled(self):
        for payload in [b'not-json',b'\xff',[],None,{}, {'choices': []}, {'choices':[None]},
                        {'choices':[{'finish_reason':'stop','message':None}]}, self.response([]),self.response({'description':'only'})]:
            with self.subTest(payload=repr(payload)):
                with self.assertRaises(ValidationError): self.invoke(payload)
    def test_truncated_refusal_and_tool_calls_rejected(self):
        for field,value in [('finish_reason','length'),('finish_reason','content_filter'),('refusal','refused'),('tool_calls',[{}]),('role','user')]:
            response=self.response()
            if field=='finish_reason':response['choices'][0][field]=value
            else:response['choices'][0]['message'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValidationError):self.invoke(response)
    def test_oversized_response_rejected(self):
        with self.assertRaisesRegex(ValidationError,'limit'):self.invoke(b' '*(MAX_LLAMACPP_RESPONSE_BYTES+1))
    def test_network_error_is_redacted(self):
        for error in [urllib.error.URLError('sensitive-error-body'), TimeoutError('sensitive-error-body'),
                      ConnectionResetError('sensitive-error-body'), urllib.error.HTTPError('http://localhost',500,'sensitive-error-body',{},None)]:
            with self.subTest(type=type(error).__name__),self.assertRaises(ValidationError) as caught:self.invoke(error)
            self.assertNotIn('sensitive',str(caught.exception))
            self.assertTrue(caught.exception.__suppress_context__)
    def test_master_fields_html_wrong_type_and_length_rejected(self):
        valid={'description':'A','short_description':'B','image_alt':'C'}
        for change in [{'regular_price':'1'},{'stock_quantity':0},{'name':'bad'},{'status':'publish'},
                       {'description':'<script>x</script>'},{'image_alt':5},{'image_alt':'x'*501}]:
            with self.subTest(change=repr(change)),self.assertRaises(ValidationError):self.invoke(self.response(valid|change))

if __name__=='__main__':unittest.main()
