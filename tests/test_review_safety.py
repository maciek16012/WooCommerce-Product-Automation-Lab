"""Regression coverage for review integrity and publication boundaries."""
import io
import json
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from woo_sync.ai_cli import main
from woo_sync.ai_providers import openai_provider
from woo_sync.content_proposals import build_proposal, set_approval, apply_approved, source_fingerprint, validate_proposal
from woo_sync.core import ProductRow, ValidationError, load_csv
from woo_sync.proposal_io import write_new_proposal, write_materialized_csv, replace_proposal, review_proposal, load_proposal
from test_llamacpp_provider import FakeOpener

class ReviewSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.row=ProductRow(2,'A-1','Klawiatura','199.00',10,'publish',{
            'description':'Old','short_description':'Short','image_id':'22','image_alt':'Keyboard'})
    def proposal(self):
        return build_proposal([self.row],lambda row:{'description':'New'},'catalog.json')
    def approved(self):return set_approval(self.proposal(),'A-1','approved')
    def test_pending_content_is_not_applied(self):
        self.assertEqual(apply_approved([self.row],self.proposal()),[self.row])
    def test_manual_approval_flag_without_review_is_rejected(self):
        p=self.proposal();p['items'][0]['approval']='approved'
        with self.assertRaisesRegex(ValidationError,'zatwierdzenia'):apply_approved([self.row],p)
    def test_edit_after_approval_requires_new_review(self):
        p=self.approved();p['items'][0]['proposed']['description']='Unreviewed'
        with self.assertRaisesRegex(ValidationError,'zatwierdzenia'):apply_approved([self.row],p)
        p=set_approval(p,'A-1','approved')
        self.assertEqual(apply_approved([self.row],p)[0].extra['description'],'Unreviewed')
    def test_copied_review_to_other_proposal_rejected(self):
        p=self.approved();p['proposal_id']='a'*32
        with self.assertRaises(ValidationError):apply_approved([self.row],p)
    def test_all_master_fields_are_forbidden(self):
        for field in ('name','regular_price','stock_quantity','status','categories','image_id','image_url','approval'):
            with self.subTest(field=field),self.assertRaises(ValidationError):
                build_proposal([self.row],lambda row:{field:'bad'},'catalog.json')
    def test_provider_cannot_mutate_source_or_fingerprint(self):
        fingerprint=source_fingerprint(self.row)
        def provider(row):row.extra['image_id']='999';return {'description':'New'}
        proposal=build_proposal([self.row],provider,'catalog.json')
        self.assertEqual(source_fingerprint(self.row),fingerprint)
        self.assertEqual(proposal['items'][0]['source_fingerprint'],fingerprint)
    def test_absent_and_empty_have_different_source_fingerprints(self):
        a=replace(self.row,extra={});b=replace(self.row,extra={'description':''})
        self.assertNotEqual(source_fingerprint(a),source_fingerprint(b))
    def test_missing_approved_sku_rejected_by_library(self):
        with self.assertRaises(ValidationError):apply_approved([],self.approved())
    def test_stale_extra_fields_are_blocked(self):
        p=self.approved();row=replace(self.row,extra=self.row.extra|{'image_id':'33'})
        with self.assertRaisesRegex(ValidationError,'źródło zmieniło się'):apply_approved([row],p)
    def test_schema_rejects_invalid_sku_id_and_fingerprint(self):
        for field,value in [('sku',123),('source_fingerprint','z'*64)]:
            p=self.proposal();p['items'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValidationError):validate_proposal(p)
        p=self.proposal();p.pop('proposal_id')
        with self.assertRaises(ValidationError):validate_proposal(p)
    def test_sparse_optional_fields_rejected_before_output(self):
        path=self.root/'out.csv';other=replace(self.row,sku='B-1',extra={})
        with self.assertRaisesRegex(ValidationError,'mieszanych'):write_materialized_csv(path,[self.row,other])
        self.assertFalse(path.exists())
    def test_invalid_materialization_not_published(self):
        path=self.root/'out.csv';row=replace(self.row,extra=self.row.extra|{'image_alt':''})
        with self.assertRaises(ValidationError):write_materialized_csv(path,[row])
        self.assertFalse(path.exists());self.assertEqual(list(self.root.glob('*.tmp')),[])
    def test_csv_normalization_must_not_change_approved_text(self):
        path=self.root/'out.csv';row=replace(self.row,extra=self.row.extra|{'description':' padded '})
        with self.assertRaisesRegex(ValidationError,'Normalizacja'):write_materialized_csv(path,[row])
        self.assertFalse(path.exists())
    def test_proposal_write_failure_leaves_no_partial_file(self):
        path=self.root/'p.json'
        with patch('woo_sync.proposal_io.os.fsync',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):write_new_proposal(path,self.proposal())
        self.assertFalse(path.exists());self.assertEqual(list(self.root.glob('*.tmp')),[])
    def test_review_replace_failure_keeps_original(self):
        path=self.root/'p.json';write_new_proposal(path,self.proposal());old=path.read_bytes()
        with patch('woo_sync.proposal_io.os.replace',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):replace_proposal(path,self.approved())
        self.assertEqual(path.read_bytes(),old);self.assertEqual(list(self.root.glob('*.tmp')),[])
    def test_existing_csv_is_never_overwritten(self):
        path=self.root/'out.csv';path.write_text('keep')
        with self.assertRaises(ValidationError):write_materialized_csv(path,[self.row])
        self.assertEqual(path.read_text(),'keep')
    def test_review_round_trip_binds_content(self):
        path=self.root/'p.json';write_new_proposal(path,self.proposal())
        review_proposal(path,'A-1','approved')
        self.assertEqual(apply_approved([self.row],load_proposal(path))[0].extra['description'],'New')
    def test_propose_existing_output_does_not_call_provider(self):
        path=self.root/'p.json';path.write_text('keep')
        with patch('woo_sync.ai_cli.load_source') as source,patch('sys.stderr',new_callable=io.StringIO):
            self.assertEqual(main(['propose','absent.json','--provider','llamacpp','--out',str(path)]),2)
            source.assert_not_called()
    def test_review_lock_blocks_concurrent_decision(self):
        from woo_sync.locking import sync_lock
        path=self.root/'p.json';write_new_proposal(path,self.proposal())
        with sync_lock(path.with_name(path.name+'.lock')):
            with self.assertRaises(ValidationError):review_proposal(path,'A-1','approved')
        self.assertEqual(load_proposal(path)['items'][0]['approval'],'pending')

    def test_oversized_proposal_rejected(self):
        path=self.root/'p.json';path.write_text(' '*20)
        with patch('woo_sync.proposal_io.MAX_PROPOSAL_BYTES',10),self.assertRaisesRegex(ValidationError,'limit'):load_proposal(path)

class OpenAiSafetyTests(unittest.TestCase):
    def invoke(self,payload):
        import os
        row=ProductRow(1,'A','A','1.00',1,'draft',{})
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'},clear=True),patch('woo_sync.ai_providers.urllib.request.build_opener',return_value=FakeOpener(payload)):
            return openai_provider(row)
    def test_bad_envelope_is_validation_error(self):
        for response in [[],{}, {'status':'completed','output':[None]}, {'status':'completed','output':[{'type':'message','content':None}]}]:
            with self.subTest(response=response),self.assertRaises(ValidationError):self.invoke(response)
    def test_valid_json_with_master_field_is_rejected(self):
        generated={'description':'A','short_description':'B','image_alt':'C','regular_price':'1'}
        response={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(generated)}]}]}
        with self.assertRaises(ValidationError):self.invoke(response)
    def test_refusal_after_text_is_not_ignored(self):
        response={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'{}'},{'type':'refusal'}]}]}
        with self.assertRaisesRegex(ValidationError,'odmówił'):self.invoke(response)

if __name__=='__main__':unittest.main()
