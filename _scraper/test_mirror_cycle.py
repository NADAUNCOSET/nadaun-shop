"""Regression checks for cadence, access holds and isolated publication."""
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
import json,os,subprocess,tempfile,unittest
import socket
from mirror_schedule import ROOT,freshness,controls
from mirror_runtime import ensure,prepare_publication,synchronize_master,git,head
from mirror_cycle import cycle_lock,adapter_implemented

@contextmanager
def fixture_root():
    base=ROOT/'_private/catalog/test-runtime/mirror-cycle';base.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as temp:
        root=Path(temp).resolve()/'fixture';(root/'_scraper').mkdir(parents=True)
        (root/'_scraper/mirror-policy.json').write_text(json.dumps({'schema_version':1,'confirmed_by':'owner','refresh_interval_seconds':432000,'collection_concurrency':1,'failed_or_partial_inventory_removes_products':False}))
        (root/'_scraper/partner-sync-plan.json').write_text(json.dumps({'sources':{'supplier':{'refresh_interval_seconds':432000}}}))
        yield root

def repository(root):
    git(root,'init','-q');git(root,'config','user.name','Mirror fixture');git(root,'config','user.email','mirror-fixture@example.invalid');git(root,'config','commit.gpgsign','false')
    (root/'generated.json').write_text('old');(root/'_scraper/operator.py').write_text('committed')
    git(root,'add','.');git(root,'commit','-q','-m','baseline')

class MirrorCycleTests(unittest.TestCase):
    def test_five_day_boundary_and_future_time_fail_closed(self):
        with fixture_root() as root:
            snap={'complete':True,'collected_at':'2026-10-01T00:00:00+00:00'};start=datetime(2026,10,1,tzinfo=timezone.utc).timestamp()
            self.assertFalse(freshness(snap,'supplier',root,start+431999)['due'])
            self.assertTrue(freshness(snap,'supplier',root,start+432000)['due'])
            self.assertTrue(freshness(snap,'supplier',root,start-1)['due'])
            self.assertTrue(freshness(snap|{'complete':False},'supplier',root,start+1)['due'])
    def test_attempt_time_never_counts_as_supplier_observation(self):
        with fixture_root() as root:
            now=datetime(2026,10,30,tzinfo=timezone.utc).timestamp();s={'complete':True,'collected_at':'2026-10-01T00:00:00+00:00','last_attempt_at':'2026-10-30T00:00:00+00:00'}
            self.assertTrue(freshness(s,'supplier',root,now)['due'])
    def test_source_hold_and_unresolved_parser_error_block_before_requests(self):
        with fixture_root() as root:
            folder=root/'_scraper/.sync-state/supplier';folder.mkdir(parents=True)
            p=folder/'source-suspended.json';p.write_text(json.dumps({'suspended':True,'reason':'owner review'}));self.assertTrue(controls('supplier',root)['blocked'])
            p.write_text(json.dumps({'suspended':False}));e=folder/'worker-error.json';e.write_text(json.dumps({'requires_review':True}));self.assertTrue(controls('supplier',root)['blocked'])
            e.write_text(json.dumps({'requires_review':True,'resolved':True}));self.assertFalse(controls('supplier',root)['blocked'])
    def test_uncommitted_operator_code_is_preserved_while_generated_copy_syncs(self):
        with fixture_root() as root:
            repository(root);runtime=ensure(root);(root/'_scraper/operator.py').write_text('operator in progress');(runtime/'generated.json').write_text('new')
            with patch.dict(os.environ,{'NADAUN_SHOP_MASTER_ROOT':str(root)}):
                proof=prepare_publication(runtime,['generated.json']);self.assertTrue(proof['backup_verified'])
                git(runtime,'add','generated.json');git(runtime,'commit','-q','-m','generated refresh');commit=head(runtime);synchronize_master(runtime,proof,commit)
            self.assertEqual((root/'generated.json').read_text(),'new');self.assertEqual((root/'_scraper/operator.py').read_text(),'operator in progress');self.assertEqual(head(root),commit)
            self.assertEqual(git(root,'diff','--name-only').decode().strip(),'_scraper/operator.py')
    def test_edited_generated_target_blocks_before_copy_or_publication(self):
        with fixture_root() as root:
            repository(root);runtime=ensure(root);(runtime/'generated.json').write_text('new');(root/'generated.json').write_text('operator edits')
            with patch.dict(os.environ,{'NADAUN_SHOP_MASTER_ROOT':str(root)}),self.assertRaisesRegex(RuntimeError,'Operator generated file'):
                prepare_publication(runtime,['generated.json'])
            self.assertEqual((root/'generated.json').read_text(),'operator edits')
    def test_source_policy_edit_blocks_runtime_setup(self):
        with fixture_root() as root:
            (root/'data/catalog').mkdir(parents=True);p=root/'data/catalog/brand-source-policy.json';p.write_text('{}');repository(root);p.write_text('{"operator":"editing"}')
            with self.assertRaisesRegex(RuntimeError,'policy is being edited'):ensure(root)
    def test_cycle_lease_prevents_a_second_process_and_does_not_steal_foreign_host(self):
        with fixture_root() as root:
            with cycle_lock(root):
                with self.assertRaises(BlockingIOError):
                    with cycle_lock(root):pass
            lock=root/'_scraper/.sync-state/mirror-cycle.lock'
            self.assertFalse(lock.exists());lock.write_text(json.dumps({'host':'other-computer','pid':1234}))
            with self.assertRaisesRegex(BlockingIOError,'another computer'):
                with cycle_lock(root):pass
            self.assertTrue(lock.exists())
    def test_adapter_label_alone_never_counts_as_an_implemented_collector(self):
        with fixture_root() as root:
            self.assertFalse(adapter_implemented('gauphoto',root));self.assertFalse(adapter_implemented('motion9',root))
            (root/'_scraper/manual_source_worker.py').write_text('fixture')
            self.assertTrue(adapter_implemented('motion9',root))

if __name__=='__main__':unittest.main()
