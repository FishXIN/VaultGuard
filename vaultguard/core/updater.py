"""版本更新检测：查询 GitHub Releases，比对当前版本是否落后。

只依赖标准库（urllib），不引入额外第三方依赖；检测放在后台线程执行，
任何网络/解析异常都安静吞掉，绝不影响主程序运行。
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.request
from dataclasses import dataclass
from typing import Optional

from .. import __version__

# 发布仓库（见 project_memory：https://github.com/FishXIN/VaultGuard）
_REPO = "FishXIN/VaultGuard"
_RELEASES_API = f"https://api.github.com/repos/{_REPO}/releases"
_RELEASES_PAGE = f"https://github.com/{_REPO}/releases/latest"
_TIMEOUT = 8


@dataclass
class ReleaseInfo:
    """一次成功检测到的可更新发布信息。"""
    version: str            # 规范化后的版本号（去掉前缀 v）
    tag: str                # 原始 tag，如 v0.1.6
    name: str               # Release 标题
    notes: str              # Release 正文（更新说明）
    html_url: str           # Release 网页地址（下载页）
    prerelease: bool        # 是否预发布


def _parse_version(text: str) -> tuple[int, ...]:
    """把 'v0.1.5' / '0.1.5-beta.1' 解析为可比较的数字元组。

    仅取主体的数字段（major.minor.patch...），忽略预发布后缀，
    保证 '0.1.5' 与 '0.1.5-beta' 主体一致时按相等处理（足够用于"是否更新"判断）。
    """
    core = text.strip().lstrip("vV").split("-")[0].split("+")[0]
    parts = re.findall(r"\d+", core)
    return tuple(int(p) for p in parts) if parts else (0,)


def _is_newer(remote: str, local: str) -> bool:
    return _parse_version(remote) > _parse_version(local)


def _fetch_releases() -> list[dict]:
    req = urllib.request.Request(
        _RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "VaultGuard-UpdateChecker",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data if isinstance(data, list) else []


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
    try:
        releases = _fetch_releases()
    except Exception:  # noqa: BLE001 网络/解析失败时静默
        return None

    candidates = [
        r for r in releases
        if not r.get("draft")
        and (include_prerelease or not r.get("prerelease"))
        and r.get("tag_name")
    ]
    if not candidates:
        return None

    # 选出版本号最大的一条
    best = max(candidates, key=lambda r: _parse_version(r["tag_name"]))
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
