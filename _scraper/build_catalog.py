# -*- coding: utf-8 -*-
"""[통합으로 대체됨 2026-07-20] catalog.html(브랜드별)은 이제 build_shop.py가 생성.
   12 고정 대분류 IA + 브랜드별/제품별 토글. 옛 브랜드우선 빌더=_archive/build_catalog_brandfirst_20260720.py.
   파이프라인 호환용 얇은 래퍼(두 파일 함께 생성)."""
import build_shop
build_shop.main()
