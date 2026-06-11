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
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from .. import __version__

# 发布仓库（见 project_memory：https://github.com/FishXIN/VaultGuard）
_REPO = "FishXIN/VaultGuard"
_ATOM_FEED = f"https://github.com/{_REPO}/releases.atom"
_RELEASES_API = f"https://api.github.com/repos/{_REPO}/releases"
_RELEASES_PAGE = f"https://github.com/{_REPO}/releases/latest"
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
