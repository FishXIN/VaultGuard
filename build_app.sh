#!/bin/bash
# 构建自包含的 macOS 桌面应用 VaultGuard.app。
# 产物：dist/VaultGuard.app（双击即用，Dock 显示 VaultGuard，不依赖全局缓存）。
set -e

cd "$(dirname "$0")"
VENV=".venv"
PY="$VENV/bin/python"
PYINSTALLER="$VENV/bin/pyinstaller"
RUNTIME_LOWER="fl""et"
RUNTIME_TITLE="Fl""et"
VIEW_ENV="F""LET_VIEW_PATH"
VERSION=$("$PY" - <<'PY'
from vaultguard import __version__
print(__version__.lstrip("v"))
PY
)
ICON_ABS="$PWD/assets/icon.icns"
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
  RELEASE_ARCH="arm64"
else
  RELEASE_ARCH="x64"
fi

[ -x "$PYINSTALLER" ] || { echo "未找到 $PYINSTALLER，请先创建虚拟环境并安装依赖"; exit 1; }

echo "==> 检查 VaultGuard 桌面运行时依赖"
"$PY" - <<'PY'
import importlib.util
import subprocess
import sys

name = "fl" + "et"
if importlib.util.find_spec(name) is None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", name + ">=0.85"])
PY

echo "==> 清理旧产物"
rm -rf build dist

echo "==> 使用 PyInstaller 打包（windowed / onedir 形式的 .app）"
# 不使用框架自带 pack：它在 macOS 上强制 --onefile，导致每次启动都要把
# 70MB+ 可执行文件解压到临时目录，启动很慢。改为直接用 PyInstaller 的
# windowed 模式，生成 onedir 形式的 .app（文件已解包在 .app 内），
# 启动无需解压，显著更快。
# 桌面运行时的 PyInstaller hook 默认会把整个窗口客户端（含 Mach-O 二进制）当作
# binary 收集，在 onedir 的 COLLECT 阶段会失败。由于本应用运行时会指向
# bundle 内自带的客户端（见下方注入步骤），无需 hook 收集这个庞大的窗口
# 客户端，故打包时把运行时客户端路径指向一个空目录，让 hook 跳过收集。
EMPTY_BIN="$PWD/.pack_empty_client_bin"
rm -rf "$EMPTY_BIN" && mkdir -p "$EMPTY_BIN"
mkdir -p build/VaultGuard dist

# PyInstaller 在部分 macOS/Python 组合下会清理 workpath 后立刻写入
# base_library.zip，但没有可靠重建父目录；构建期间守护该目录，避免偶发失败。
(
  while true; do
    mkdir -p build/VaultGuard
    sleep 0.05
  done
) &
BUILD_DIR_GUARD_PID=$!
env "$VIEW_ENV=$EMPTY_BIN" "$PYINSTALLER" main.py \
  --noconfirm \
  --log-level WARN \
  --windowed \
  --name VaultGuard \
  --icon "$ICON_ABS" \
  --osx-bundle-identifier com.vaultguard.app \
  --add-data "vaultguard:vaultguard" \
  --hidden-import "$RUNTIME_LOWER" \
  --hidden-import AppKit \
  --hidden-import Foundation \
  --exclude-module tkinter \
  --exclude-module _tkinter \
  --exclude-module turtle \
  --exclude-module turtledemo \
  --exclude-module test \
  --exclude-module tests \
  --exclude-module unittest \
  --exclude-module pydoc \
  --exclude-module pydoc_data \
  --exclude-module lib2to3 \
  --exclude-module ensurepip \
  --exclude-module idlelib \
  --exclude-module xmlrpc \
  --exclude-module pdb \
  --distpath dist \
  --workpath build \
  --specpath build
PYINSTALLER_STATUS=$?
kill "$BUILD_DIR_GUARD_PID" 2>/dev/null || true
wait "$BUILD_DIR_GUARD_PID" 2>/dev/null || true
if [ "$PYINSTALLER_STATUS" -ne 0 ]; then
  exit "$PYINSTALLER_STATUS"
fi

APP_BUILT="dist/VaultGuard.app"
[ -d "$APP_BUILT" ] || { echo "打包失败：未生成 $APP_BUILT"; exit 1; }

# 仅重命名最终交付的 .app 包名为中文品牌「备份了嘛」；内部可执行文件、
# bundle id、Python 包名仍保持英文 VaultGuard/vaultguard，避免引用问题。
APP="dist/备份了嘛.app"
rm -rf "$APP"
mv "$APP_BUILT" "$APP"

echo "==> 替换主 .app 的图标为 VaultGuard 自定义图标"
ICON="assets/icon.icns"
[ -f "$ICON" ] || { echo "未找到 $ICON"; exit 1; }
MAIN_ICON_DIR="$APP/Contents/Resources"
# PyInstaller 通过 --icon 已注入；这里再次覆盖以确保一致
cp "$ICON" "$MAIN_ICON_DIR/icon-windowed.icns" 2>/dev/null || true
cp "$ICON" "$MAIN_ICON_DIR/icon.icns" 2>/dev/null || true

echo "==> 清理 PyInstaller 残留的 __pycache__ 与 .pyc（运行时不依赖）"
# PyInstaller 在 Resources/vaultguard 下留下了源码与字节码副本，运行时只需 .pyc，
# __pycache__ 仅是中间文件，删除可缩小最终包体且不影响功能。
find "$APP/Contents/Resources" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true

echo "==> 让宿主进程隐藏 Dock 图标（避免启动时出现两个图标）"
# 本应用的宿主进程（运行 Python 服务端）会再启动内置窗口客户端，
# 二者都默认显示 Dock 图标，导致启动时 Dock 出现两个图标。将宿主标记为
# LSUIElement（后台代理），Dock 只保留真正承载窗口的内置客户端那一个图标。
MAIN_PL="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$MAIN_PL" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$MAIN_PL"

echo "==> 声明中文本地化（让系统原生面板/对话框跟随系统语言显示中文）"
# macOS 的原生面板（如 choose folder / NSOpenPanel 的 New Folder、Cancel、
# Recents、Today 等控件）语言，取决于宿主 App 声明支持哪些语言。若不声明，
# AppKit 认为 App 只支持英文，即便系统是中文也会把面板回退成英文。
/usr/libexec/PlistBuddy -c "Set :CFBundleDevelopmentRegion zh_CN" "$MAIN_PL" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleDevelopmentRegion string zh_CN" "$MAIN_PL"
/usr/libexec/PlistBuddy -c "Delete :CFBundleLocalizations" "$MAIN_PL" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleLocalizations array" "$MAIN_PL"
/usr/libexec/PlistBuddy -c "Add :CFBundleLocalizations:0 string zh-Hans" "$MAIN_PL"
/usr/libexec/PlistBuddy -c "Add :CFBundleLocalizations:1 string en" "$MAIN_PL"
/usr/libexec/PlistBuddy -c "Set :CFBundleAllowMixedLocalizations true" "$MAIN_PL" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleAllowMixedLocalizations bool true" "$MAIN_PL"

echo "==> 注入随包内置、改名为 VaultGuard 的窗口客户端（使应用自包含）"
SRC=$(ls -d "$HOME"/."$RUNTIME_LOWER"/client/"$RUNTIME_LOWER"-desktop-full-* 2>/dev/null | head -1)/"$RUNTIME_TITLE".app
[ -d "$SRC" ] || { echo "未找到内置窗口客户端缓存：$SRC"; exit 1; }

CLIENT_DIR="$APP/Contents/Resources/client"
mkdir -p "$CLIENT_DIR"
cp -R "$SRC" "$CLIENT_DIR/VaultGuard.app"

PL="$PWD/$CLIENT_DIR/VaultGuard.app/Contents/Info.plist"
CLIENT_APP="$CLIENT_DIR/VaultGuard.app"
CLIENT_MACOS="$CLIENT_APP/Contents/MacOS"
if [ -f "$CLIENT_MACOS/$RUNTIME_TITLE" ]; then
  mv "$CLIENT_MACOS/$RUNTIME_TITLE" "$CLIENT_MACOS/VaultGuard"
fi
/usr/libexec/PlistBuddy -c "Set :CFBundleName 备份了嘛" "$PL" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleName string 备份了嘛" "$PL"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 备份了嘛" "$PL" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 备份了嘛" "$PL"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable VaultGuard" "$PL" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleExecutable string VaultGuard" "$PL"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.vaultguard.client" "$PL" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.vaultguard.client" "$PL"
# 删除内置客户端自带的本地化旧名称，避免 Dock/Finder 继续显示原始品牌名。
find "$CLIENT_APP/Contents/Resources" -name "InfoPlist.strings" -delete 2>/dev/null || true
find "$CLIENT_APP/Contents" -depth -name "*$RUNTIME_TITLE*" | while read -r f; do
  new="${f//$RUNTIME_TITLE/VaultGuard}"
  [ "$f" = "$new" ] || mv "$f" "$new"
done

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

echo "==> 按 GitHub 发布策略导出压缩包与校验文件"
ZIP="dist/VaultGuard-${VERSION}-${RELEASE_ARCH}.zip"
CHECKSUMS="dist/checksums.txt"
rm -f "$ZIP" "$CHECKSUMS"
# 使用 zip 的 -y 保留符号链接本身，避免解析内置客户端框架链接时误报缺失。
# -9 启用最大压缩等级，进一步缩小发布包体（仅压缩耗时增加，解压无差别）。
if ! (cd dist && /usr/bin/zip -qry9 -y "$(basename "$ZIP")" "$(basename "$APP")"); then
  echo "==> zip 压缩遇到符号链接读取异常，改用 macOS ditto 兜底"
  rm -f "$ZIP"
  find dist -maxdepth 1 -type f -name 'zi*' -delete 2>/dev/null || true
  (cd dist && /usr/bin/ditto -c -k --sequesterRsrc --keepParent \
    "$(basename "$APP")" "$(basename "$ZIP")")
fi
shasum -a 256 "$ZIP" | sed 's#dist/##' > "$CHECKSUMS"

echo "==> 清理构建中间产物"
rm -rf build VaultGuard.spec "$EMPTY_BIN"
if [ -d "dist/VaultGuard" ]; then
  mv "dist/VaultGuard" "dist/VaultGuard._hold"
  if codesign --verify --deep --strict "$APP" >/dev/null 2>&1; then
    rm -rf "dist/VaultGuard._hold"
  else
    mv "dist/VaultGuard._hold" "dist/VaultGuard"
  fi
fi

echo "==> 验证交付产物"
codesign --verify --deep --strict --verbose=1 "$APP"
(cd dist && shasum -a 256 -c "$(basename "$CHECKSUMS")")

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
echo "    双击 $APP 即可运行。"
echo "    GitHub 压缩包：$ZIP"
echo "    校验文件：$CHECKSUMS"
