"""macOS 原生目录选择器。

直接调用系统自带的 `osascript`（AppleScript 的 `choose folder`），由系统
进程弹出原生访达选择框。这样既不需要在 Flet 工作线程里直接碰 AppKit（会触发
线程安全违例导致卡顿/闪退），也不需要 spawn 我们自己的 Python/Flet 子进程
（会冒出第二个窗口或 Dock 图标）。
"""
from __future__ import annotations

import subprocess
from typing import Optional


def pick_directory(title: str) -> Optional[str]:
    """弹出系统原生访达目录选择框，返回选中的 POSIX 路径或 None。"""
    # AppleScript 的字符串需转义双引号，避免 prompt 内容破坏脚本。
    safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'set chosen to choose folder with prompt "{safe_title}"\n'
        'return POSIX path of chosen'
    )
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    # 用户点击取消时 osascript 返回非 0（-128），直接当作未选择处理。
    if proc.returncode != 0:
        return None
    path = proc.stdout.strip()
    return path or None
