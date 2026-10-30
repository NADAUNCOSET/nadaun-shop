import json,tempfile,unittest
import io
from PIL import Image
from unittest.mock import patch
from pathlib import Path
from supplier_banners import image_candidates,collect,render,ROOT

def temporary():
    folder=ROOT/'_private/catalog/test-runtime/supplier-banners';folder.mkdir(parents=True,exist_ok=True)
    return tempfile.TemporaryDirectory(dir=folder)

class SupplierBannerTests(unittest.TestCase):
    def test_largest_observed_srcset_and_lazy_original_are_selected(self):
        raw='''<div class="main-visual"><img alt="Camera" src="small.jpg" srcset="medium.jpg 960w, full.jpg 1920w"><img src="blank.gif" data-original="master.png"></div>'''
        rows=image_candidates(raw,'https://supplier.example/');self.assertEqual({r['url'] for r in rows},{'https://supplier.example/full.jpg','https://supplier.example/master.png'})
    def test_ordinary_product_carousels_and_logo_are_excluded(self):
        raw='''<ul class="prdList swiper-slide"><li><img src="goods.jpg"></li></ul><div class="main-visual"><img src="logo.png"></div>'''
        self.assertEqual(image_candidates(raw,'https://supplier.example/'),[])
    def test_protection_hold_blocks_even_force_collection(self):
        class Forbidden:
            def get(self,url):raise AssertionError('Protected supplier must not be requested')
        with temporary() as temp:
            root=Path(temp);scraper=root/'_scraper';scraper.mkdir()
            scraper.joinpath('mirror-policy.json').write_text(json.dumps({'schema_version':1,'confirmed_by':'owner','refresh_interval_seconds':432000,'collection_concurrency':1,'failed_or_partial_inventory_removes_products':False}))
            scraper.joinpath('partner-sync-plan.json').write_text(json.dumps({'sources':{'test':{'url':'https://supplier.example/'}}}))
            hold=scraper/'.sync-state/test';hold.mkdir(parents=True);hold.joinpath('source-suspended.json').write_text(json.dumps({'reason':'provider protection'}))
            result=collect(root,force=True,fetcher=Forbidden());self.assertEqual(result['sites'][0]['state'],'source_suspended');self.assertEqual(result['assets'],[])
    def test_review_paths_are_relative_and_text_is_escaped(self):
        with temporary() as temp:
            root=Path(temp);asset=root/'_private/assets/a.png';asset.parent.mkdir(parents=True);asset.write_bytes(b'fixture')
            row={'source':'<test>','url':'https://supplier.example/a.png','path':str(asset),'label':'<script>x</script>','review_state':'검토 대기','width':1000,'height':200,'frames':1}
            target=render(root,{'checked_at':'test','assets':[row],'sites':[]});page=target.read_text()
            self.assertNotIn('file://',page);self.assertIn('../../_private/assets/a.png',page);self.assertIn('&lt;script&gt;',page)
    def test_partial_site_check_keeps_other_site_age_and_does_not_skip_due_sites(self):
        class Response:
            status_code=200;content=b'<html>no banner</html>';url='https://supplier.example/'
        class Reader:
            def __init__(self):self.urls=[]
            def get(self,url):self.urls.append(url);return Response()
        with temporary() as temp:
            root=Path(temp);scraper=root/'_scraper';scraper.mkdir()
            scraper.joinpath('mirror-policy.json').write_text(json.dumps({'schema_version':1,'confirmed_by':'owner','refresh_interval_seconds':432000,'collection_concurrency':1,'failed_or_partial_inventory_removes_products':False}))
            scraper.joinpath('partner-sync-plan.json').write_text(json.dumps({'sources':{'one':{'url':'https://one.example/'},'two':{'url':'https://two.example/'}}}))
            state=root/'_private/catalog/supplier-banners';state.mkdir(parents=True)
            state.joinpath('current.json').write_text(json.dumps({'checked_at':'2099-01-01T00:00:00+00:00','assets':[],'sites':[{'source':'two','checked_at':'2000-01-01T00:00:00+00:00','state':'old'}]}))
            reader=Reader();first=collect(root,sources=['one'],fetcher=reader)
            self.assertEqual(len(first['sites']),2);self.assertEqual(next(r for r in first['sites'] if r['source']=='two')['checked_at'],'2000-01-01T00:00:00+00:00')
            second=collect(root,fetcher=reader);self.assertEqual(reader.urls,['https://one.example/','https://two.example/'])
    def test_changed_bytes_at_the_same_banner_url_are_archived_on_refresh(self):
        class Response:
            status_code=200
            def __init__(self,url,content):self.url=url;self.content=content
        class Reader:
            color='red'
            def get(self,url):
                if not url.endswith('.png'):return Response(url,b'<div class="main-visual"><img src="banner.png"></div>')
                data=io.BytesIO();Image.new('RGB',(800,200),self.color).save(data,format='PNG');return Response(url,data.getvalue())
        with temporary() as temp:
            root=Path(temp);s=root/'_scraper';s.mkdir()
            (s/'mirror-policy.json').write_text(json.dumps({'schema_version':1,'confirmed_by':'owner','refresh_interval_seconds':432000,'collection_concurrency':1,'failed_or_partial_inventory_removes_products':False}))
            (s/'partner-sync-plan.json').write_text(json.dumps({'sources':{'one':{'url':'https://one.example/'}}}))
            reader=Reader();first=collect(root,force=True,fetcher=reader);digest=first['assets'][0]['sha256']
            reader.color='blue';second=collect(root,force=True,fetcher=reader)
            self.assertEqual(len(second['assets']),2);self.assertFalse(second['assets'][0]['current']);self.assertEqual(second['assets'][1]['supersedes_sha256'],digest)
            third=collect(root,force=True,fetcher=reader);self.assertEqual(len(third['assets']),2)
if __name__=='__main__':unittest.main()
