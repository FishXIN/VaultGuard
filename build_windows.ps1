param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Venv = ".venv-win"
$Py = Join-Path $Venv "Scripts\python.exe"
$PyInstaller = Join-Path $Venv "Scripts\pyinstaller.exe"

if (-not (Test-Path $Py)) {
    Write-Host "==> 创建 Windows 虚拟环境"
    py -3 -m venv $Venv
}

if (-not $SkipInstall) {
    Write-Host "==> 安装 Windows 打包依赖"
    & $Py -m pip install --upgrade pip
    & $Py -m pip install -r requirements.txt
    & $Py -m pip install "flet>=0.85" pyinstaller pillow
}

$Version = (& $Py -c "from vaultguard import __version__; print(__version__.lstrip('v'))").Trim()
$Arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x64" }
$ReleaseAppDir = "dist\VaultGuard-windows-$Arch"

Write-Host "==> 准备 Windows 图标"
$Ico = "assets\icon.ico"
if (-not (Test-Path $Ico)) {
    @'
from pathlib import Path
from PIL import Image

src = Path("assets/icon_1024.png")
dst = Path("assets/icon.ico")
if not src.exists():
    raise SystemExit("未找到 assets/icon_1024.png，无法生成 Windows .ico")

img = Image.open(src).convert("RGBA")
img.save(dst, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
'@ | & $Py -
}

Write-Host "==> 清理旧 Windows 产物"
New-Item -ItemType Directory -Force -Path dist | Out-Null
Remove-Item -Recurse -Force build\windows, dist\windows -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $ReleaseAppDir -ErrorAction SilentlyContinue
Get-ChildItem dist -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "VaultGuard-windows-*" } |
    Remove-Item -Recurse -Force
Get-ChildItem dist -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -like "VaultGuard-*-windows-*.zip" -or
        $_.Name -like "VaultGuard-Setup-*-*.exe" -or
        $_.Name -like "VaultGuard-*-*.msi"
    } |
    Remove-Item -Force

Write-Host "==> 使用 PyInstaller 打包 Windows onedir 应用"
& $PyInstaller main.py `
    --noconfirm `
    --clean `
    --windowed `
    --name VaultGuard `
    --icon $Ico `
    --add-data "vaultguard;vaultguard" `
    --hidden-import flet `
    --hidden-import tkinter `
    --hidden-import tkinter.filedialog `
    --distpath dist\windows `
    --workpath build\windows

$AppDir = "dist\windows\VaultGuard"
if (-not (Test-Path $AppDir)) {
    throw "打包失败：未生成 $AppDir"
}

Write-Host "==> 同步 Windows 测试应用到 dist 目录"
Copy-Item -Recurse -Force $AppDir $ReleaseAppDir
$ReleaseExe = Join-Path $ReleaseAppDir "VaultGuard.exe"
if (-not (Test-Path $ReleaseExe)) {
    throw "未在 dist 目录找到 Windows exe：$ReleaseExe"
}

Write-Host "==> 按 GitHub 发布策略导出 Windows 压缩包与校验文件"
$Zip = "dist\VaultGuard-$Version-windows-$Arch.zip"
Compress-Archive -Path "$ReleaseAppDir\*" -DestinationPath $Zip -Force

$ChecksumFile = "dist\checksums.txt"
Get-ChildItem dist -File |
    Where-Object {
        $_.Name -like "VaultGuard-*.zip" -or
        $_.Name -like "VaultGuard-Setup-*.exe" -or
        $_.Name -like "VaultGuard-*.msi"
    } |
    Sort-Object Name |
    ForEach-Object {
        $hash = Get-FileHash -Algorithm SHA256 $_.FullName
        "$($hash.Hash.ToLower())  $($_.Name)"
    } |
    Set-Content -Path $ChecksumFile -Encoding ascii

Write-Host "==> 验证 Windows 压缩包"
if (-not (Test-Path $Zip)) {
    throw "未生成 Windows 压缩包：$Zip"
}

Write-Host "==> 清理 Windows 构建中间产物"
Remove-Item -Recurse -Force build\windows -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force dist\windows -ErrorAction SilentlyContinue
Remove-Item -Force VaultGuard.spec -ErrorAction SilentlyContinue

Write-Host "==> 完成"
Write-Host "    Windows 应用目录：$ReleaseAppDir"
Write-Host "    Windows 测试 exe：$ReleaseExe"
Write-Host "    Windows 压缩包：$Zip"
Write-Host "    校验文件：$ChecksumFile"
