#!/usr/bin/env python3
"""VaultGuard 图形界面入口。

运行：python main.py
"""
import os
import sys

if __name__ == "__main__":
    # 子进程模式：仅弹出原生目录选择器后退出。必须在导入 app（会拉起 flet
    # 运行时与全部业务模块）之前短路，否则每次弹窗都要白白加载整个 GUI 框架，
    # 导致面板打开明显卡顿。
    if os.environ.get("VAULTGUARD_DIR_PICKER") == "1":
        from vaultguard.ui.dirpicker import run_picker_process
        run_picker_process()
    else:
        from vaultguard.ui.app import run
        run()
