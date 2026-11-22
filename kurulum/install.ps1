# DosyaKit kurulumu (yönetici izni gerektirmez; sadece bu kullanıcıya kurar)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Info($m) { Write-Host "  $m" -ForegroundColor Gray }
function Step($m) { Write-Host ""; Write-Host "» $m" -ForegroundColor Cyan }
function Fail($m) { Write-Host ""; Write-Host "HATA: $m" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  DosyaKit kurulumu" -ForegroundColor White
Write-Host "  Klasör: $Root" -ForegroundColor DarkGray

# ---------------------------------------------------------------- 1. Python
Step "Python aranıyor"

function Test-Py($exe, $pre) {
    try {
        $args2 = @($pre) + @("-c", "import sys; print('%d.%d' % sys.version_info[:2]); sys.exit(0 if sys.version_info >= (3, 9) else 3)")
        $args2 = $args2 | Where-Object { $_ -ne $null -and $_ -ne "" }
        $out = & $exe @args2 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return $true }
    } catch { }
    return $false
}

$PyExe = $null; $PyPre = $null
$candidates = @(
    @{ exe = "py"; pre = "-3" },
    @{ exe = "python"; pre = "" }
)
Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | ForEach-Object { $candidates += @{ exe = $_.FullName; pre = "" } }
Get-ChildItem "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | ForEach-Object { $candidates += @{ exe = $_.FullName; pre = "" } }

foreach ($c in $candidates) {
    if (Test-Py $c.exe $c.pre) { $PyExe = $c.exe; $PyPre = $c.pre; break }
}

if (-not $PyExe) {
    Info "Python 3.9+ bulunamadı. winget ile Python 3.12 kuruluyor…"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "winget yok. Python'u https://www.python.org/downloads/ adresinden kurun (kurulumda 'Add python.exe to PATH' işaretleyin) ve bu kurulumu tekrar çalıştırın."
    }
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    $p = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($p -and (Test-Py $p.FullName "")) { $PyExe = $p.FullName; $PyPre = "" }
    else { Fail "Python kuruldu ama bulunamadı. Bilgisayarı yeniden başlatıp kurulumu tekrar çalıştırın." }
}
$ver = if ($PyPre) { & $PyExe $PyPre --version } else { & $PyExe --version }
Info "Bulundu: $ver"

# ---------------------------------------------------------------- 2. Sanal ortam ve paketler
Step "Sanal ortam hazırlanıyor (.venv)"
$Venv = Join-Path $Root ".venv"
$VPy = Join-Path $Venv "Scripts\python.exe"
$VPyw = Join-Path $Venv "Scripts\pythonw.exe"
if (-not (Test-Path $VPy)) {
    if ($PyPre) { & $PyExe $PyPre -m venv $Venv } else { & $PyExe -m venv $Venv }
    if ($LASTEXITCODE -ne 0) { Fail "Sanal ortam oluşturulamadı." }
}

Step "Kütüphaneler kuruluyor (ilk seferde birkaç dakika sürebilir)"
& $VPy -m pip install --upgrade pip --disable-pip-version-check -q
& $VPy -m pip install -r (Join-Path $Root "requirements.txt") --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Fail "Kütüphaneler kurulamadı. İnternet bağlantınızı kontrol edip tekrar deneyin." }

# Hızlı kendini test
& $VPy -c "import sys; sys.path.insert(0, r'$Root'); from app import registry; registry.load_tools(); print('  %d araç yüklendi' % len(registry.TOOLS)); sys.exit(1 if registry.LOAD_ERRORS else 0)"
if ($LASTEXITCODE -ne 0) { Write-Host "  Uyarı: bazı araçlar yüklenemedi; ayrıntı için 'DosyaKit (konsol).bat' ile başlatın." -ForegroundColor Yellow }

# ---------------------------------------------------------------- 3. Kısayollar
Step "Kısayollar oluşturuluyor"
$Launcher = Join-Path $Root "DosyaKit.pyw"
$Icon = Join-Path $Root "app\web\icon.ico"
$Shell = New-Object -ComObject WScript.Shell

function New-Shortcut($path) {
    $s = $Shell.CreateShortcut($path)
    $s.TargetPath = $VPyw
    $s.Arguments = "`"$Launcher`""
    $s.WorkingDirectory = $Root
    $s.IconLocation = $Icon
    $s.Description = "DosyaKit - dosya dönüştürücü"
    $s.Save()
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$StartMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "DosyaKit.lnk"
$SendTo = Join-Path ([Environment]::GetFolderPath("SendTo")) "DosyaKit.lnk"
New-Shortcut (Join-Path $Desktop "DosyaKit.lnk"); Info "Masaüstü kısayolu"
New-Shortcut $StartMenu; Info "Başlat menüsü"
New-Shortcut $SendTo; Info "Sağ tık > Gönder > DosyaKit"

# ---------------------------------------------------------------- 4. Sağ tık menüsü
Step "Sağ tık menüsü ekleniyor"
$Exts = ".pdf", ".doc", ".docx", ".odt", ".rtf", ".ppt", ".pptx", ".odp", ".xls", ".xlsx", ".ods", ".csv",
        ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp"
$Cmd = "`"$VPyw`" `"$Launcher`" `"%1`""
foreach ($e in $Exts) {
    $key = "HKCU:\Software\Classes\SystemFileAssociations\$e\shell\DosyaKit"
    New-Item -Path "$key\command" -Force | Out-Null
    Set-Item -Path $key -Value "DosyaKit ile işle"
    New-ItemProperty -Path $key -Name "Icon" -Value $Icon -PropertyType String -Force | Out-Null
    Set-Item -Path "$key\command" -Value $Cmd
}
Info "$($Exts.Count) dosya türü için eklendi (Windows 11'de: sağ tık > Diğer seçenekleri göster)"

# ---------------------------------------------------------------- 5. Ofis motoru kontrolü
Step "Ofis dönüşüm motoru kontrol ediliyor"
& $VPy -c "import sys; sys.path.insert(0, r'$Root'); from app.engines import office; s = office.status(); ms = s['msoffice']; print('  Microsoft Office: ' + (', '.join(k for k, v in ms.items() if v) or 'yok')); print('  LibreOffice: ' + (s['libreoffice'] or 'yok'))"
Write-Host "  (Word/PowerPoint/Excel → PDF için Microsoft Office veya ücretsiz LibreOffice gerekir;" -ForegroundColor DarkGray
Write-Host "   PDF → Word/PPT/Excel ve tüm PDF araçları ek bir program olmadan çalışır.)" -ForegroundColor DarkGray

Write-Host ""
Write-Host "Kurulum tamamlandı! DosyaKit açılıyor…" -ForegroundColor Green
Start-Process -FilePath $VPyw -ArgumentList "`"$Launcher`"" -WorkingDirectory $Root
