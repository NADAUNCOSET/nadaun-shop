from datetime import datetime, timezone
import plistlib
from pathlib import Path
import subprocess
import json
import hashlib
import tempfile
import unittest
from mirror_audit import saved_source, scheduler_inventory, age_hours, source_paths, completion_issues, unavailable_exclusions, offer_comparison, source_controls, pending_runs


class MirrorAuditTests(unittest.TestCase):
    def test_latest_private_run_replaces_historical_run_and_checks_the_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base=root/'_private/catalog';base.mkdir(parents=True)
            old=base/'mirror-refresh-20261027';new=base/'mirror-completion-20261030'
            old.mkdir();new.mkdir()
            (base/'mirror-audit-latest.json').write_text('{}')
            (old/'plthink-run.json').write_text(json.dumps({'source':'plthink','state':'collected_verified','finished_at':'2026-10-27T10:00:00Z'}))
            (new/'plthink-run.json').write_text(json.dumps({'source':'plthink','phase':'running','at':'2026-10-30T03:00:00Z','published':False}))
            (new/'START.json').write_text(json.dumps({'jobs':[{'source':'plthink','pid':123}]}))
            command='python '+str(new/'collect-pending.py')+' plthink'
            result=pending_runs(root,{123:command})['plthink']
            self.assertEqual(result['state'],'running')
            self.assertTrue(result['process_observed_running'])
            self.assertFalse(result['published_flag_in_run'])
            self.assertFalse(pending_runs(root,{})['plthink']['process_observed_running'])
            self.assertFalse(pending_runs(root,{123:'python unrelated.py plthink'})['plthink']['process_observed_running'])

    def setUp(self):
        self.now=datetime(2026,10,29,12,tzinfo=timezone.utc)
        self.snapshot={'source':'example','complete':True,'collected_at':'2026-10-29T11:00:00Z',
                       'product_count':2,'products':{'a':{},'b':{}}}

    def test_same_count_with_missing_and_wrong_ids_never_passes(self):
        result=saved_source('example',self.snapshot,[{'id':'a'},{'id':'c'}],{'a','b'},self.now)
        self.assertFalse(result['live_offer_ids_equal'])
        self.assertEqual(result['missing_offer_ids'],['b'])
        self.assertEqual(result['unexpected_offer_ids'],['c'])

    def test_duplicate_live_offers_and_partial_snapshot_are_attention_items(self):
        result=saved_source('example',self.snapshot|{'complete':False},[{'id':'a'},{'id':'a'}],{'a'},self.now)
        self.assertIn('duplicate_live_offer_ids',result['issues'])
        self.assertIn('snapshot_incomplete_or_count_mismatch',result['issues'])

    def test_stale_or_undated_source_is_not_fresh_even_when_ids_match(self):
        for value in ['2026-10-27T11:00:00Z',None,'2026-10-29T13:00:00Z','2026-10-29T11:00:00']:
            result=saved_source('example',self.snapshot|{'collected_at':value},[{'id':'a'},{'id':'b'}],{'a','b'},self.now)
            self.assertTrue(result['live_offer_ids_equal'])
            self.assertTrue(any('source_' in issue for issue in result['issues']))
        self.assertEqual(age_hours('2026-10-29T20:00:00+09:00',self.now),1)

    def test_saved_plist_is_not_proof_of_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'co.nadaun.shop.clmedia-sync.plist'
            p.write_bytes(plistlib.dumps({'Label':p.stem,'ProgramArguments':['python','worker']}))
            result=scheduler_inventory(Path(tmp),lambda *a,**k:subprocess.CompletedProcess(a[0],113,'',''))
            self.assertFalse(result[p.stem]['registered'])

    def test_hipixel_uses_its_actual_dedicated_worker_not_the_general_catalog_timer(self):
        with tempfile.TemporaryDirectory() as tmp:
            schedules={'co.nadaun.shop.hipixel-sync':{'registered':True},'co.nadaun.shop.catalog-sync':{'registered':False}}
            result=source_controls(Path(tmp),'hipixel',{},schedules)
            self.assertTrue(result['scheduler_registered'])
            self.assertEqual(result['scheduler_labels'],['co.nadaun.shop.hipixel-sync'])

    def test_unavailable_exclusion_requires_exact_cached_identity_guard(self):
        from enrich_shop_sources import shard,source_fingerprint
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pid='kpp-1';raw={'id':pid,'name':'original','price':100,'sale_price':100,'supplier_status':'soldout'}
            path=root/'data/catalog/source-details/kpp'/(shard(pid)+'.json');path.parent.mkdir(parents=True)
            path.write_text(json.dumps({pid:{'detail_status':'verified','unavailable':True,'source_fingerprint':source_fingerprint(raw)}}))
            self.assertIn(pid,unavailable_exclusions(root,'kpp',{pid:raw},{pid}))
            self.assertEqual(unavailable_exclusions(root,'kpp',{pid:raw|{'name':'different model'}},{pid}),{})

    def test_price_and_stock_differences_are_detected_for_the_same_product_id(self):
        raw={'id':'motion9-1','sale_price':10000,'status':'inquiry','source_url':'https://example.com/1'}
        snapshot={'products':{raw['id']:raw}}
        offer={'id':raw['id'],'price':10500,'status':'inquiry','url':raw['source_url']}
        self.assertEqual(offer_comparison(Path('/unused'),'motion9',snapshot,[offer])['differences'],[])
        result=offer_comparison(Path('/unused'),'motion9',snapshot,[offer|{'price':10000,'status':'soldout'}])
        self.assertEqual({v['field'] for v in result['differences']},{'price','status'})

    def test_matching_live_counts_and_unbound_acceptance_cannot_self_certify_complete(self):
        report={'revision':'new','live_catalog_equal':True,'catalog_errors':[],
                'sources':[{'source':'example','source_sha256':'new-hash','issues':[]}],
                'gift':{'all_current_details_verified':True,'full_source_inventory_verified':True,'live_equal_to_nas':True,'source_access':'ready'}}
        for acceptance in [{},{'revision':'old','source_sha256':{'example':'new-hash'}},
                           {'revision':'new','source_sha256':{'example':'old-hash'}}]:
            issues=completion_issues(report,acceptance,Path('/unused'),self.now)
            self.assertIn('end_to_end_evidence_missing_or_stale',issues)

    def test_completion_evidence_must_be_current_and_content_bound(self):
        report={'revision':'new','live_catalog_equal':True,'catalog_errors':[],
                'sources':[{'source':'example','source_sha256':'hash','issues':[]}],
                'gift':{'all_current_details_verified':True,'full_source_inventory_verified':True,'live_equal_to_nas':True,'source_access':'ready'}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);proof=root/'proof.json';proof.write_text('{"verified":"combined end-to-end review"}')
            value={'path':'proof.json','checked_at':self.now.isoformat(),'sha256':hashlib.sha256(proof.read_bytes()).hexdigest()}
            acceptance={'revision':'new','source_sha256':{'example':'hash'},'proofs':{k:value for k in ['inventory','details','options_prices_stock','images_identity','legacy_links','browser']}}
            self.assertEqual(completion_issues(report,acceptance,root,self.now),[])
            proof.write_text('changed after verification')
            self.assertTrue(completion_issues(report,acceptance,root,self.now))

    def test_discovery_keeps_all_current_sources_and_ignores_retired_duplicate_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'data/catalog/sources';out.mkdir(parents=True)
            for name in ['kpp','smartstore','motion9','sunphoto','avx-aputure','avx-approved','imweb-dji','nadaun-gift']:
                (out/(name+'.json')).write_text('{}')
            result=source_paths(root)
            self.assertEqual(set(result),{'kpp','smartstore','motion9','sunphoto','avx'})
            self.assertEqual(result['avx'].name,'avx-approved.json')


if __name__=='__main__':unittest.main()
