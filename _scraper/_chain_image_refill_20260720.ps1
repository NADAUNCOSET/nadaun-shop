# 이미지 결손 재수집 체인 2026-07-20: firstmall(avx,aurora,green) -> woo(tov). 순차(데이터 파일 공유).
$wd = '\\Nadaunproject\nadaunproject\_Site\nadaun-shop\_scraper'
Set-Location $wd
& python -u firstmall_supervisor.py avx aurora green 2>&1 | Out-File -Append -Encoding utf8 (Join-Path $wd '_refill_firstmall_20260720.log')
& python -u woo.py tov ALL 2>&1 | Out-File -Append -Encoding utf8 (Join-Path $wd '_refill_tov_20260720.log')
'REFILL CHAIN DONE ' + (Get-Date -Format 'yyyy-MM-dd HH:mm') | Out-File -Append -Encoding utf8 (Join-Path $wd '_refill_chain_20260720.done.log')
