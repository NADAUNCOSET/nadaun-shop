# Chain runner 2026-07-17: wait for green supervisor to finish, then run woo -> saeki.
# Done-detection: green resume log idle > 20 min (supervisor prints at least every 600s while alive).
$wd  = '\\Nadaunproject\nadaunproject\_Site\nadaun-shop\_scraper'
$log = Join-Path $wd '_supervisor_20260717_2051_green_resume.log'
Set-Location $wd

while ($true) {
    Start-Sleep -Seconds 120
    $f = Get-Item $log -ErrorAction SilentlyContinue
    if ($null -eq $f) { break }
    if (((Get-Date) - $f.LastWriteTime).TotalMinutes -gt 20) { break }
}

& python -u woo.py tov ALL 2>&1 | Out-File -Append -Encoding utf8 (Join-Path $wd '_woo_20260717.log')
& python -u saeki.py ALL   2>&1 | Out-File -Append -Encoding utf8 (Join-Path $wd '_saeki_20260717.log')
'CHAIN DONE ' + (Get-Date -Format 'yyyy-MM-dd HH:mm') | Out-File -Append -Encoding utf8 (Join-Path $wd '_chain_woo_saeki_20260717.done.log')
