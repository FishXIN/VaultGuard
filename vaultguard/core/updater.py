"""版本更新检测：查询 GitHub Releases，比对当前版本是否落后。

只依赖标准库（urllib + xml），不引入额外第三方依赖；检测放在后台线程执行，
任何网络/解析异常都安静吞掉，绝不影响主程序运行。

数据源优先级：
1. github.com 的 releases.atom 订阅源——不走 REST API，不受 60 次/小时 的
   未认证限流约束，是最稳定的来源；
2. api.github.com/releases——作为兜底（可能命中 403 rate limit）。
"""
from __future__ import annotations

import json
import os
import platform
import re
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, Optional

from .. import __version__

# 发布仓库（见 project_memory：https://github.com/FishXIN/VaultGuard）
_REPO = "FishXIN/VaultGuard"
_ATOM_FEED = f"https://github.com/{_REPO}/releases.atom"
_RELEASES_API = f"https://api.github.com/repos/{_REPO}/releases"
_RELEASES_PAGE = f"https://github.com/{_REPO}/releases/latest"
_DOWNLOAD_BASE = f"https://github.com/{_REPO}/releases/download"
_TIMEOUT = 8
_UA = "VaultGuard-UpdateChecker"


@dataclass
class ReleaseInfo:
    """一次成功检测到的可更新发布信息。"""
    version: str            # 规范化后的版本号（去掉前缀 v）
    tag: str                # 原始 tag，如 v0.1.7
    name: str               # Release 标题
    notes: str              # Release 正文（更新说明，可能为空）
    html_url: str           # Release 网页地址（下载页）
    prerelease: bool        # 是否预发布（atom 源无法判定时为 False）


def _parse_version(text: str) -> tuple[int, ...]:
    """把 'v0.1.7' / '0.1.7-beta.1' 解析为可比较的数字元组。

    仅取主体的数字段（major.minor.patch...），忽略预发布后缀，
    保证 '0.1.7' 与 '0.1.7-beta' 主体一致时按相等处理（足够用于"是否更新"判断）。
    """
    core = text.strip().lstrip("vV").split("-")[0].split("+")[0]
    parts = re.findall(r"\d+", core)
    return tuple(int(p) for p in parts) if parts else (0,)


def _is_newer(remote: str, local: str) -> bool:
    return _parse_version(remote) > _parse_version(local)


def _http_get(url: str, accept: str) -> bytes:
    req = urllib.request.Request(
        url, headers={"Accept": accept, "User-Agent": _UA})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as resp:
        return resp.read()


def _candidates_from_atom() -> list[dict]:
    """解析 releases.atom，返回 [{tag, name, notes, html_url}]。"""
    raw = _http_get(_ATOM_FEED, "application/atom+xml")
    root = ET.fromstring(raw)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out: list[dict] = []
    for entry in root.findall("a:entry", ns):
        link_el = entry.find("a:link", ns)
        html_url = link_el.get("href") if link_el is not None else ""
        # tag 优先从链接 .../releases/tag/<tag> 提取，退化用 <id> 末段
        tag = ""
        if html_url and "/tag/" in html_url:
            tag = html_url.rsplit("/tag/", 1)[-1]
        if not tag:
            id_el = entry.find("a:id", ns)
            if id_el is not None and id_el.text:
                tag = id_el.text.rsplit("/", 1)[-1]
        if not tag:
            continue
        title_el = entry.find("a:title", ns)
        content_el = entry.find("a:content", ns)
        out.append({
            "tag_name": tag,
            "name": (title_el.text if title_el is not None else tag) or tag,
            "body": (content_el.text if content_el is not None else "") or "",
            "html_url": html_url or _RELEASES_PAGE,
            "prerelease": False,
        })
    return out


def _candidates_from_api(include_prerelease: bool) -> list[dict]:
    raw = _http_get(_RELEASES_API, "application/vnd.github+json")
    data = json.loads(raw.decode("utf-8"))
    releases = data if isinstance(data, list) else []
    return [
        {
            "tag_name": r.get("tag_name"),
            "name": r.get("name") or r.get("tag_name"),
            "body": r.get("body") or "",
            "html_url": r.get("html_url") or _RELEASES_PAGE,
            "prerelease": bool(r.get("prerelease")),
        }
        for r in releases
        if not r.get("draft")
        and (include_prerelease or not r.get("prerelease"))
        and r.get("tag_name")
    ]


def check_for_update(
    current_version: Optional[str] = None,
    include_prerelease: bool = True,
) -> Optional[ReleaseInfo]:
    """检测是否有比当前版本更新的发布。

    返回 ReleaseInfo 表示有可用更新；返回 None 表示已是最新或检测失败。
    include_prerelease=True 时也会把预发布（alpha/beta/rc）纳入候选，
    因为当前发布渠道仍以 Pre-release 形式分发。
    """
    local = current_version or __version__

    candidates: list[dict] = []
    try:
        candidates = _candidates_from_atom()
    except Exception:  # noqa: BLE001 atom 失败时回退到 API
        try:
            candidates = _candidates_from_api(include_prerelease)
        except Exception:  # noqa: BLE001 两条路都失败则静默
            return None
    candidates = [c for c in candidates if c.get("tag_name")]
    if not candidates:
        return None

    # 选出版本号最大的一条
    best = max(candidates, key=lambda c: _parse_version(c["tag_name"]))
    tag = best["tag_name"]
    if not _is_newer(tag, local):
        return None

    return ReleaseInfo(
        version=tag.strip().lstrip("vV"),
        tag=tag,
        name=best.get("name") or tag,
        notes=best.get("body") or "",
        html_url=best.get("html_url") or _RELEASES_PAGE,
        prerelease=bool(best.get("prerelease")),
    )


def _current_arch() -> str:
    """归一化当前 CPU 架构为发布产物使用的 arm64 / x64。"""
    m = (platform.machine() or "").lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    return "x64"


def asset_url(info: ReleaseInfo) -> tuple[str, str]:
    """按发布产物命名规范，拼出当前平台安装包的 (下载直链, 文件名)。

    命名规范（见 VaultGuard_GitHub发布策略.md / build 脚本）：
    - macOS：  VaultGuard-<版本>-<arm64|x64>.zip
    - Windows：VaultGuard-<版本>-windows-<arm64|x64>.zip
    """
    arch = _current_arch()
    ver = info.version
    if sys.platform.startswith("win"):
        name = f"VaultGuard-{ver}-windows-{arch}.zip"
    else:
        name = f"VaultGuard-{ver}-{arch}.zip"
    return f"{_DOWNLOAD_BASE}/{info.tag}/{name}", name


def _list_release_assets(tag: str) -> list[str]:
    """获取指定 tag 下真实存在的资产下载直链。

    优先解析 github.com 的 expanded_assets 页面（不走 API、不限流），
    失败再退回 REST API。任一来源失败都返回空列表。
    """
    urls: list[str] = []
    # 1) expanded_assets 页面
    try:
        page = f"https://github.com/{_REPO}/releases/expanded_assets/{tag}"
        html = _http_get(page, "text/html").decode("utf-8", "ignore")
        urls = re.findall(
            rf"/{_REPO}/releases/download/[^\"'> ]+", html)
        urls = ["https://github.com" + u for u in urls]
    except Exception:  # noqa: BLE001
        urls = []
    if urls:
        return sorted(set(urls))
    # 2) REST API 兜底
    try:
        raw = _http_get(f"{_RELEASES_API}/tags/{tag}",
                        "application/vnd.github+json")
        data = json.loads(raw.decode("utf-8"))
        return [a.get("browser_download_url")
                for a in data.get("assets", [])
                if a.get("browser_download_url")]
    except Exception:  # noqa: BLE001
        return []


def _pick_platform_asset(urls: list[str]) -> Optional[str]:
    """从资产直链列表中，按当前平台与架构挑出最合适的安装包。"""
    arch = _current_arch()
    is_win = sys.platform.startswith("win")
    is_mac = sys.platform == "darwin"

    def name_of(u: str) -> str:
        return u.rsplit("/", 1)[-1].lower()

    # 仅考虑安装包格式
    pkgs = [u for u in urls
            if name_of(u).endswith((".zip", ".dmg", ".exe", ".msi"))]
    if not pkgs:
        return None

    def score(u: str) -> int:
        n = name_of(u)
        s = 0
        # 平台匹配（Windows 资产名含 windows / .exe / .msi）
        win_like = ("windows" in n or n.endswith((".exe", ".msi")))
        if is_win and win_like:
            s += 100
        elif (is_mac or not is_win) and not win_like:
            s += 100
        # 架构匹配
        if arch in n:
            s += 10
        elif arch == "x64" and ("amd64" in n or "x86_64" in n):
            s += 10
        return s

    best = max(pkgs, key=score)
    # 至少要平台匹配上才采用，否则视为未找到
    return best if score(best) >= 100 else None


def resolve_asset_url(info: ReleaseInfo) -> tuple[str, str]:
    """定位当前平台安装包的 (下载直链, 文件名)。

    优先用 release 的真实资产清单匹配，避免命名偏差导致 404；
    匹配不到时退回按规范硬拼的链接。
    """
    try:
        urls = _list_release_assets(info.tag)
        picked = _pick_platform_asset(urls)
        if picked:
            return picked, picked.rsplit("/", 1)[-1]
    except Exception:  # noqa: BLE001
        pass
    return asset_url(info)


def download_asset(
    info: ReleaseInfo,
    dest_dir: str,
    progress: Optional[Callable[[int, int], None]] = None,
) -> str:
    """下载当前平台安装包到 dest_dir，返回落地文件的完整路径。

    progress(downloaded_bytes, total_bytes) 回调用于上报进度；
    total 未知时传 0。下载失败会抛出异常，由调用方处理。
    """
    url, name = resolve_asset_url(info)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)
    tmp = dest + ".part"

    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if progress is not None:
                    try:
                        progress(done, total)
                    except Exception:  # noqa: BLE001 进度回调异常不影响下载
                        pass
    os.replace(tmp, dest)
    return dest


def can_self_install() -> bool:
    """当前运行形态是否支持「下载后原地替换并重启」。

    仅打包后的桌面应用（PyInstaller frozen）才有确定的安装位置可替换；
    源码 / 开发态没有可替换的 bundle，返回 False，由调用方退回手动方式。
    """
    if not getattr(sys, "frozen", False):
        return False
    try:
        return _install_target() is not None
    except Exception:  # noqa: BLE001
        return False


def _install_target() -> Optional[str]:
    """推导当前应用应被替换的根路径。

    - macOS：承载本进程的 .app bundle（exe 上溯三级，形如 .../备份了嘛.app）。
    - Windows / Linux：可执行文件所在目录（onedir 形态的整包目录）。
    无法确定时返回 None。
    """
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        bundle = exe.parents[2] if len(exe.parents) >= 3 else None
        if bundle is not None and bundle.suffix == ".app" and bundle.is_dir():
            return str(bundle)
        return None
    parent = exe.parent
    return str(parent) if parent.is_dir() else None


def install_update(zip_path: str) -> bool:
    """以脱离主进程的方式安装已下载的新版本压缩包，并在替换后重启应用。

    流程（在独立子进程脚本中执行，确保本进程退出后才动手）：
    1. 等待当前进程（pid）退出，释放对自身文件的占用；
    2. 解压新包到临时目录；
    3. 删除旧的应用并把新应用移动到原位置；
    4. 重新拉起新应用。

    成功派生安装脚本返回 True（调用方应随即退出本进程）；
    不支持自安装（如开发态）或派生失败返回 False。
    """
    if not can_self_install():
        return False
    target = _install_target()
    if not target or not os.path.isfile(zip_path):
        return False
    pid = os.getpid()
    try:
        if sys.platform == "darwin":
            return _spawn_installer_macos(zip_path, target, pid)
        if sys.platform.startswith("win"):
            return _spawn_installer_windows(zip_path, target, pid)
        return False
    except Exception:  # noqa: BLE001 派生失败则退回手动方式
        return False


def _spawn_installer_macos(zip_path: str, bundle: str, pid: int) -> bool:
    import subprocess
    import tempfile

    script = f"""#!/bin/sh
ZIP={_sh_quote(zip_path)}
BUNDLE={_sh_quote(bundle)}
PID={pid}
# 1) 等旧进程退出，释放对自身 bundle 的占用
i=0
while /bin/kill -0 "$PID" 2>/dev/null; do
  /bin/sleep 0.2
  i=$((i+1))
  [ "$i" -gt 150 ] && break
done
STAGING=$(/usr/bin/mktemp -d /tmp/vaultguard_update.XXXXXX) || exit 1
# 2) 解压新包（产物顶层即 .app）
/usr/bin/ditto -x -k "$ZIP" "$STAGING" 2>/dev/null || /usr/bin/unzip -oq "$ZIP" -d "$STAGING"
NEW_APP=$(/bin/ls -d "$STAGING"/*.app 2>/dev/null | /usr/bin/head -1)
if [ -d "$NEW_APP" ]; then
  # 3) 删除旧 app，移入新 app
  /bin/rm -rf "$BUNDLE"
  /bin/mv "$NEW_APP" "$BUNDLE"
  /usr/bin/xattr -dr com.apple.quarantine "$BUNDLE" 2>/dev/null || true
  # 4) 重新拉起
  /usr/bin/open -n "$BUNDLE"
fi
/bin/rm -rf "$STAGING"
/bin/rm -f "$ZIP"
"""
    fd, path = tempfile.mkstemp(suffix=".sh", prefix="vaultguard_update_")
    with os.fdopen(fd, "w") as fh:
        fh.write(script)
    os.chmod(path, 0o755)
    subprocess.Popen(
        ["/bin/sh", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True


def _spawn_installer_windows(zip_path: str, app_dir: str, pid: int) -> bool:
    import subprocess
    import tempfile

    exe = os.path.join(app_dir, "VaultGuard.exe")
    script = f"""@echo off
setlocal
set "ZIP={zip_path}"
set "APPDIR={app_dir}"
set "EXE={exe}"
set "PID={pid}"
:waitloop
tasklist /FI "PID eq %PID%" 2>NUL | find "%PID%" >NUL
if not errorlevel 1 (
  timeout /t 1 /nobreak >NUL
  goto waitloop
)
set "STAGING=%TEMP%\\vaultguard_update_%PID%"
rmdir /S /Q "%STAGING%" 2>NUL
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '%STAGING%' -Force"
robocopy "%STAGING%" "%APPDIR%" /MIR /NFL /NDL /NJH /NJS /NP >NUL
rmdir /S /Q "%STAGING%" 2>NUL
del /F /Q "%ZIP%" 2>NUL
start "" "%EXE%"
del /F /Q "%~f0" 2>NUL
"""
    fd, path = tempfile.mkstemp(suffix=".bat", prefix="vaultguard_update_")
    with os.fdopen(fd, "w") as fh:
        fh.write(script)
    subprocess.Popen(
        ["cmd", "/c", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return True


def _sh_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)
