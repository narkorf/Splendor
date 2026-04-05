param(
    [string]$PythonLauncher = "py",
    [string]$AppName = "SplendorDesktop"
)

$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DistDir = Join-Path $RootDir "dist"
$AppDir = Join-Path $DistDir $AppName
$ZipPath = Join-Path $DistDir "$AppName-windows.zip"
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $RootDir ".pyinstaller"

Set-Location $RootDir

if (Test-Path $VenvPython) {
    & $VenvPython -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --name $AppName `
        --add-data "splendor_app/assets;splendor_app/assets" `
        packaging_launcher.py
} else {
    & $PythonLauncher -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name $AppName `
    --add-data "splendor_app/assets;splendor_app/assets" `
    packaging_launcher.py
}

if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

Compress-Archive -Path (Join-Path $AppDir "*") -DestinationPath $ZipPath -Force

Write-Host "Created Windows build artifacts:"
Write-Host "  App folder: $AppDir"
Write-Host "  Zip file: $ZipPath"
