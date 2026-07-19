#!/usr/bin/env bash
# 자동 마무리 체인 2026-07-20 (대표 취침 중 "쭉 진행"): firstmall catwalk 완료 대기 →
# 이미지 폴백 → 카테고리 트리 적용 → 재빌드4종 → 커밋+배포. 진행은 _autobuild_20260720.log.
D="//Nadaunproject/nadaunproject/_Site/nadaun-shop/_scraper"
SHOP="//Nadaunproject/nadaunproject/_Site/nadaun-shop"
FM="$D/_catwalk_firstmall_20260720.log"
LOG="$D/_autobuild_20260720.log"
cd "$D" || exit 1

echo "[$(date +%H:%M:%S)] START — firstmall catwalk 완료 대기" > "$LOG"
for i in $(seq 1 180); do
  sleep 60
  if grep -q "WALK DONE" "$FM" 2>/dev/null; then echo "[$(date +%H:%M:%S)] catwalk 완료 감지" >> "$LOG"; break; fi
done

echo "[$(date +%H:%M:%S)] STEP1 thumb_fallback --apply" >> "$LOG"
python -X utf8 thumb_fallback.py --apply >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] STEP2 rebuild_cat_paths --apply" >> "$LOG"
python -X utf8 rebuild_cat_paths.py --apply >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] STEP3 build_brands" >> "$LOG";           python -X utf8 build_brands.py >> "$LOG" 2>&1
echo "[$(date +%H:%M:%S)] STEP3 build_catalog" >> "$LOG";          python -X utf8 build_catalog.py >> "$LOG" 2>&1
echo "[$(date +%H:%M:%S)] STEP3 build_catalog_category" >> "$LOG"; python -X utf8 build_catalog_category.py >> "$LOG" 2>&1
echo "[$(date +%H:%M:%S)] STEP3 build_detail" >> "$LOG";           python -X utf8 build_detail.py >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] STEP4 git commit + push" >> "$LOG"
git -C "$SHOP" add -A >> "$LOG" 2>&1
git -C "$SHOP" commit -F "$D/_autobuild_commitmsg.txt" >> "$LOG" 2>&1
git -C "$SHOP" push origin main >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] AUTOBUILD DONE" >> "$LOG"
