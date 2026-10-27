# Сборка выпуска App Design Studio: тесты → PyInstaller → самопроверка EXE → portable ZIP → (Inno Setup).
# Запуск из корня проекта: powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
$version = (& $py -c "from app import APP_VERSION; print(APP_VERSION)").Trim()
Write-Host "App Design Studio $version"

& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Тесты не прошли" }

& $py -m PyInstaller packaging\AppDesignStudio.spec --noconfirm --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller завершился с ошибкой" }
$exe = Join-Path $root "dist\AppDesignStudio\AppDesignStudio.exe"

# самопроверка без Python в окружении
$report = Join-Path $env:TEMP "ads_smoke_build.json"
$saved = @{ PATH = $env:PATH; PYTHONPATH = $env:PYTHONPATH; PYTHONHOME = $env:PYTHONHOME; VIRTUAL_ENV = $env:VIRTUAL_ENV }
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    Remove-Item Env:PYTHONPATH, Env:PYTHONHOME, Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $exe -ArgumentList "--smoke-test", "`"$report`"" -Wait -PassThru
} finally {
    foreach ($k in $saved.Keys) { if ($saved[$k]) { Set-Item "Env:$k" $saved[$k] } }
}
$r = Get-Content $report -Raw -Encoding UTF8 | ConvertFrom-Json
if ($p.ExitCode -ne 0 -or -not $r.ok) { throw "Самопроверка собранной программы не прошла: $report" }
Write-Host "Самопроверка: OK ($($r.total_ms) мс)"

$zip = Join-Path $root "dist\AppDesignStudio-$version-win64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $root "dist\AppDesignStudio") -DestinationPath $zip
Write-Host "Portable: $zip"

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc "/DAppVersion=$version" packaging\AppDesignStudio.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup завершился с ошибкой" }
} else {
    Write-Host "Inno Setup 6 не найден — установщик не собран (portable ZIP готов)."
}
