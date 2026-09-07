import unittest

from shipping_policy import shipping_class


class ShippingTest(unittest.TestCase):
    def classify(self, name, kind='purchase', override=None):
        return shipping_class({'id':'test','name':name,'kind':kind},override)

    def test_heavy_stands_and_complete_arm_kits(self):
        for name in ['KUPO CS-40MK C STAND KIT','Matthews C+Stand Kit (Arm 102cm)',
                     'PRO-40TK C스탠드 그립암 세트 터틀베이스형',
                     '고독스 Godox 270CS C스탠드 그립헤드 암세트',
                     'KUPO WIND-UP LOW BASE STAND','KUPO STEEL COLUMN ROLLER STAND',
                     '조명 콤보 스탠드','Air-cushioned heavy duty light stand']:
            with self.subTest(name=name):self.assertEqual(self.classify(name),'heavy_stand')

    def test_parts_and_lightweight_tripods_do_not_inherit_stand_fee(self):
        for name in ['VL-033 C스탠드 그립헤드 16mm','VL-40DGA C스탠드 그립암 세트',
                     'Wheels for C-stand','C-Stand Column 29','C-Stand Base',
                     'C-STAND CASE','PRO-M03 미니 C스탠드', '콤보 스탠드봉',
                     '조명 C스탠드용 어댑터','카메라 여행용 삼각대','마이크 스탠드',
                     'C622 SMALL STEEL STAND EXTENSION']:
            with self.subTest(name=name):self.assertEqual(self.classify(name),'standard')

    def test_rental_is_not_purchase_shipping_and_owner_override_wins(self):
        self.assertIsNone(self.classify('C STAND','rental'))
        self.assertEqual(self.classify('새 중량 스탠드',override='heavy_stand'),'heavy_stand')
        self.assertEqual(self.classify('C STAND',override='standard'),'standard')
        with self.assertRaises(ValueError):self.classify('상품',override='free')


if __name__=='__main__':unittest.main()
