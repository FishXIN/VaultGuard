#!/usr/bin/env python3
"""VaultGuard 图形界面入口。

运行：python main.py
"""
import os
import sys

if __name__ == "__main__":
    # 子进程模式必须在导入 app（会拉起 Flet）之前短路。
    if os.environ.get("VAULTGUARD_HEALTH_WORKER") == "1":
        from vaultguard.core.disk_health import run_health_worker
        run_health_worker()
    elif os.environ.get("VAULTGUARD_COPY_WORKER") == "1":
        from vaultguard.core.copy_worker import run as run_copy_worker
        run_copy_worker()
    elif os.environ.get("VAULTGUARD_DIR_PICKER") == "1":
        from vaultguard.ui.dirpicker import run_picker_process
        run_picker_process()
    else:
        from vaultguard.ui.app import run
        run()
