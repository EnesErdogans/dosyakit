# DosyaKit kaldırma: kısayolları, sağ tık menüsünü ve sanal ortamı siler.
# Proje dosyalarınıza (app klasörü) ve çıktı klasörünüze dokunmaz.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "  DosyaKit kaldırılıyor…" -ForegroundColor White

# Çalışıyorsa kapat
$rt = Join-Path $env:LOCALAPPDATA "DosyaKit\runtime.json"
if (Test-Path $rt) {
    try {
        $j = Get-Content $rt -Raw | ConvertFrom-Json
        Invoke-RestMethod -Uri "http://127.0.0.1:$($j.port)/api/shutdown" -Method Post -Headers @{ "X-Token" = $j.token } -TimeoutSec 3 | Out-Null
        Start-Sleep -Seconds 1
    } catch { }
}

$links = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "DosyaKit.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "DosyaKit.lnk"),
    (Join-Path ([Environment]::GetFolderPath("SendTo")) "DosyaKit.lnk")
)
foreach ($l in $links) { if (Test-Path $l) { Remove-Item $l -Force; Write-Host "  Silindi: $l" } }

Get-ChildItem "HKCU:\Software\Classes\SystemFileAssociations" -ErrorAction SilentlyContinue | ForEach-Object {
    $k = Join-Path $_.PSPath "shell\DosyaKit"
    if (Test-Path $k) { Remove-Item $k -Recurse -Force }
}
Write-Host "  Sağ tık menüsü kaldırıldı"

$venv = Join-Path $Root ".venv"
if (Test-Path $venv) { Remove-Item $venv -Recurse -Force; Write-Host "  Sanal ortam silindi" }

$data = Join-Path $env:LOCALAPPDATA "DosyaKit"
if (Test-Path $data) { Remove-Item $data -Recurse -Force; Write-Host "  Geçici dosyalar ve ayarlar silindi" }

Write-Host ""
Write-Host "Tamamlandı. Bu klasörü artık silebilirsiniz: $Root" -ForegroundColor Green
