"""跨平台原生目录选择器。

原生面板（macOS 的 NSOpenPanel / Windows 的文件夹对话框）都必须运行在拥有
自己事件循环的进程主线程上，而 Flet 的事件回调跑在工作线程中，直接调用会触发
线程安全违例，表现为卡顿甚至闪退。为彻底隔离，这里把面板放进一个独立子进程
运行：子进程拥有干净的主线程与自己的应用实例，弹窗结束后把选中路径写入一个
临时文件再退出（Windows 的 --windowed 进程没有可用 stdout，故统一用临时文件
回传结果）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

_OUT_ENV = "VAULTGUARD_DIR_PICKER_OUT"


def _pick_macos(title: str) -> Optional[str]:
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
            return str(urls[0].path())
    return None


def _pick_windows(title: str) -> Optional[str]:
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    # 置顶并抢占焦点，避免对话框出现在主窗口后面。
    root.attributes("-topmost", True)
    root.update()
    try:
        path = filedialog.askdirectory(title=title, mustexist=True)
    finally:
        root.destroy()
    return path or None


def run_picker_process() -> None:
    """子进程入口：弹出原生面板，把选中路径写入临时文件后退出。"""
    title = os.environ.get("VAULTGUARD_DIR_PICKER_TITLE", "选择目录")
    out_path = os.environ.get(_OUT_ENV)
    path: Optional[str] = None
    try:
        if sys.platform == "darwin":
            path = _pick_macos(title)
        elif sys.platform == "win32":
            path = _pick_windows(title)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(str(e))
    if path and out_path:
        try:
            Path(out_path).write_text(path, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    sys.exit(0)


def pick_directory(title: str) -> Optional[str]:
    """主进程调用：spawn 子进程弹出原生面板，返回选中路径或 None。"""
    out_file = tempfile.NamedTemporaryFile(
        prefix="vg_dirpick_", suffix=".txt", delete=False)
    out_file.close()
    out_path = out_file.name

    env = dict(os.environ)
    env["VAULTGUARD_DIR_PICKER"] = "1"
    env["VAULTGUARD_DIR_PICKER_TITLE"] = title
    env[_OUT_ENV] = out_path
    # 子进程不应继承内置客户端路径，避免误启 Flet 窗口。
    env.pop("FLET_VIEW_PATH", None)

    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
    else:
        main_py = Path(__file__).resolve().parents[2] / "main.py"
        cmd = [sys.executable, str(main_py)]

    try:
        subprocess.run(cmd, env=env, capture_output=True, text=True)
        try:
            content = Path(out_path).read_text(encoding="utf-8").strip()
        except OSError:
            content = ""
        return content or None
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass
