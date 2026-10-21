# -*- coding: ascii -*-
# One-click packaging script: py -3 build_exe.ps1 or run in PowerShell
$ErrorActionPreference = "Stop"
$py = "C:\Users\jimmy\.workbuddy\binaries\python\versions\3.14.3\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Set-Location $PSScriptRoot

# install pyinstaller if missing
& $py -m PyInstaller --version 2>$null
if ($LASTEXITCODE -ne 0) {
    & $py -m pip install pyinstaller
}

$iconArg = @()
if (Test-Path "assets\icon.ico") { $iconArg = @("--icon", "assets\icon.ico") }

& $py -m PyInstaller --noconfirm --clean --onefile --noconsole `
    --name "HFA" `
    @iconArg `
    --hidden-import win32timezone `
    main.py

if ($LASTEXITCODE -eq 0) {
    # remove old builds, keep only current exe
    Remove-Item -Force "dist\FGO-Assistant.exe" -ErrorAction SilentlyContinue
    # copy external assets (templates/meta/icon) next to the exe so users can edit them
    if (Test-Path "dist\assets") { Remove-Item -Recurse -Force "dist\assets" }
    Copy-Item -Recurse -Force "assets" "dist\assets"
    Remove-Item -Recurse -Force "dist\assets\_icon_work" -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "BUILD OK -> dist\HFA.exe (assets copied alongside)"
} else {
    Write-Host "BUILD FAILED"
    exit 1
}
