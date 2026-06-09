#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI 未安装，无法自动下载 artifact。"
  echo "安装后执行：brew install gh && gh auth login"
  exit 1
fi

mkdir -p dist

echo "==> 下载 GitHub Actions Windows 构建产物到 dist/"
gh run download \
  --repo "$(gh repo view --json nameWithOwner -q .nameWithOwner)" \
  --name VaultGuard-windows-dist \
  --dir dist

echo "==> 完成：dist/"
find dist -maxdepth 2 -name "VaultGuard.exe" -o -name "VaultGuard-*-windows-*.zip" -o -name "checksums.txt"
