"""macOS 原生目录选择器。

NSOpenPanel 必须运行在拥有 Cocoa runloop 的进程主线程上，而 Flet 的事件
回调跑在工作线程中，直接调用 runModal() 会触发 AppKit 线程安全违例，表现为
卡顿甚至闪退。为彻底隔离，这里把面板放进一个独立子进程运行：子进程拥有干净
的主线程与自己的 NSApplication，弹窗结束后把选中路径写到 stdout 再退出。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

_MARKER = "VGPATH:"


def run_picker_process() -> None:
    """子进程入口：弹出 NSOpenPanel，把选中路径写到 stdout 后退出。

    该函数不导入 flet，确保子进程启动尽量快。
    """
    title = os.environ.get("VAULTGUARD_DIR_PICKER_TITLE", "选择目录")
    try:
        from AppKit import NSApplication, NSOpenPanel

        app = NSApplication.sharedApplication()
        # Accessory 策略：能正常获得焦点并展示模态面板，但不在 Dock 中显示
        # 额外图标（Regular=0 会让选择器子进程在 Dock 冒出第二个图标）。
        app.setActivationPolicy_(1)

        panel = NSOpenPanel.openPanel()
        panel.setTitle_(title)
        panel.setMessage_(title)
        panel.setPrompt_("选择")
        panel.setCanChooseFiles_(False)
        panel.setCanChooseDirectories_(True)
        panel.setAllowsMultipleSelection_(False)
        panel.setCanCreateDirectories_(True)

        app.activateIgnoringOtherApps_(True)
        result = panel.runModal()
        if result == 1:
            urls = panel.URLs()
            if urls and len(urls) > 0:
                sys.stdout.write(_MARKER + str(urls[0].path()) + "\n")
                sys.stdout.flush()
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(str(e))
    sys.exit(0)


def pick_directory(title: str) -> Optional[str]:
    """主进程调用：spawn 子进程弹出原生面板，返回选中路径或 None。"""
    env = dict(os.environ)
    env["VAULTGUARD_DIR_PICKER"] = "1"
    env["VAULTGUARD_DIR_PICKER_TITLE"] = title
    # 子进程不应继承内置客户端路径，避免误启 Flet 窗口。
    env.pop("FLET_VIEW_PATH", None)

    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
    else:
        main_py = Path(__file__).resolve().parents[2] / "main.py"
        cmd = [sys.executable, str(main_py)]

    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        if line.startswith(_MARKER):
            path = line[len(_MARKER):].strip()
            return path or None
    return None
