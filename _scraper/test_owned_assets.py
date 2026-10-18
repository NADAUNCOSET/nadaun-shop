import unittest
from owned_assets import resolve_assets

class OwnedAssetTests(unittest.TestCase):
    def test_preserves_product_data_and_vendor_images(self):
        old='https://cdn.imweb.me/upload/S2020100856a601720ff3b/example.jpg'
        new='https://media.nadaun.co/shop/site-assets/example.jpg'
        vendor='https://cdn.imweb.me/upload/Svendor/example.jpg'
        value={'id':'smartstore-1','price':12345,'images':{'main':[old,vendor]}}
        result=resolve_assets(value,{old:new})
        self.assertEqual(result,{**value,'images':{'main':[new,vendor]}})
        self.assertEqual(value['images']['main'][0],old)
        self.assertEqual(resolve_assets(result,{old:new}),result)

    def test_unmigrated_old_store_image_cannot_reappear(self):
        with self.assertRaises(ValueError):
            resolve_assets(['https://cdn.imweb.me/upload/S2020100856a601720ff3b/new.jpg'],{})
        with self.assertRaises(ValueError):
            resolve_assets('https://rainbowshop.imweb.me/img/transparency.png',{})

if __name__=='__main__':unittest.main()
