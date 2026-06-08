#!/bin/bash
# 构建自包含的 macOS 桌面应用 VaultGuard.app。
# 产物：dist/VaultGuard.app（双击即用，Dock 显示 VaultGuard，不依赖全局缓存）。
set -e

cd "$(dirname "$0")"
VENV=".venv"
PY="$VENV/bin/python"
PYINSTALLER="$VENV/bin/pyinstaller"

[ -x "$PYINSTALLER" ] || { echo "未找到 $PYINSTALLER，请先创建虚拟环境并安装依赖"; exit 1; }

echo "==> 清理旧产物"
rm -rf build dist

echo "==> 使用 PyInstaller 打包（windowed / onedir 形式的 .app）"
# 不使用 flet pack：它在 macOS 上强制 --onefile，导致每次启动都要把
# 70MB+ 可执行文件解压到临时目录，启动很慢。改为直接用 PyInstaller 的
# windowed 模式，生成 onedir 形式的 .app（文件已解包在 .app 内），
# 启动无需解压，显著更快。
# flet 的 PyInstaller hook 默认会把整个 Flet.app（含 Mach-O 二进制）当作
# binary 收集，在 onedir 的 COLLECT 阶段会失败。由于本应用运行时通过
# FLET_VIEW_PATH 指向 bundle 内自带的客户端（见下方注入步骤），无需 hook
# 收集这个庞大的 Flet.app，故打包时把 FLET_VIEW_PATH 指向一个空目录，
# 让 hook 跳过收集。
EMPTY_BIN="$PWD/build/_empty_flet_bin"
rm -rf "$EMPTY_BIN" && mkdir -p "$EMPTY_BIN"
FLET_VIEW_PATH="$EMPTY_BIN" "$PYINSTALLER" main.py \
  --noconfirm \
  --windowed \
  --name VaultGuard \
  --icon assets/icon.icns \
  --osx-bundle-identifier com.vaultguard.app \
  --add-data "vaultguard:vaultguard" \
  --hidden-import AppKit \
  --hidden-import Foundation \
  --distpath dist

APP="dist/VaultGuard.app"
[ -d "$APP" ] || { echo "打包失败：未生成 $APP"; exit 1; }

echo "==> 替换主 .app 的图标为 VaultGuard 自定义图标"
ICON="assets/icon.icns"
[ -f "$ICON" ] || { echo "未找到 $ICON"; exit 1; }
MAIN_ICON_DIR="$APP/Contents/Resources"
# flet pack 通过 --icon 已注入；这里再次覆盖以确保一致
cp "$ICON" "$MAIN_ICON_DIR/icon-windowed.icns" 2>/dev/null || true
cp "$ICON" "$MAIN_ICON_DIR/icon.icns" 2>/dev/null || true

echo "==> 让宿主进程隐藏 Dock 图标（避免启动时出现两个图标）"
# 本应用的宿主进程（运行 Python/Flet 服务端）会再启动内置窗口客户端，
# 二者都默认显示 Dock 图标，导致启动时 Dock 出现两个图标。将宿主标记为
# LSUIElement（后台代理），Dock 只保留真正承载窗口的内置客户端那一个图标。
MAIN_PL="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$MAIN_PL" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$MAIN_PL"

echo "==> 注入随包内置、改名为 VaultGuard 的窗口客户端（使应用自包含）"
SRC=$(ls -d "$HOME"/.flet/client/flet-desktop-full-* 2>/dev/null | head -1)/Flet.app
[ -d "$SRC" ] || { echo "未找到 Flet 客户端缓存：$SRC"; exit 1; }

CLIENT_DIR="$APP/Contents/Resources/client"
mkdir -p "$CLIENT_DIR"
cp -R "$SRC" "$CLIENT_DIR/VaultGuard.app"

PL="$PWD/$CLIENT_DIR/VaultGuard.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName VaultGuard" "$PL"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string VaultGuard" "$PL" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName VaultGuard" "$PL"

echo "==> 替换内置客户端的图标为 VaultGuard 自定义图标"
CLIENT_RES="$CLIENT_DIR/VaultGuard.app/Contents/Resources"
# 找出 in-bundle 客户端原本的 .icns 名（通常是 AppIcon.icns），全部替换
find "$CLIENT_RES" -maxdepth 1 -name "*.icns" -print 2>/dev/null | while read -r f; do
  cp "$ICON" "$f"
done
# 兜底放一份固定名
cp "$ICON" "$CLIENT_RES/AppIcon.icns" 2>/dev/null || true
# 关键：macOS Big Sur+ 在存在 Assets.car + CFBundleIconName 时会优先使用 Assets.car 中的图标，
# 必须删除 Assets.car 并移除 CFBundleIconName 键，强制系统使用我们替换后的 AppIcon.icns。
rm -f "$CLIENT_RES/Assets.car"
/usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$PL" 2>/dev/null || true
# 让 Info.plist 指向 AppIcon
/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile AppIcon" "$PL" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "$PL" 2>/dev/null || true

echo "==> 重新签名内置客户端"
codesign --force --deep --sign - "$CLIENT_DIR/VaultGuard.app"

echo "==> 重新签名主 .app（确保 Resources 修改生效）"
codesign --force --deep --sign - "$APP"

echo "==> 刷新 LaunchServices 图标缓存"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
  -f "$APP" 2>/dev/null || true
# 触发 Finder 刷新该 .app 的图标
touch "$APP"
# 清理 IconServices 图标缓存并重启 Dock，确保 macOS 不再用旧图标
rm -rf "$HOME/Library/Caches/com.apple.iconservices.store" 2>/dev/null || true
killall Dock 2>/dev/null || true
killall Finder 2>/dev/null || true

echo "==> 完成：$APP"
echo "    双击 dist/VaultGuard.app 即可运行。"
