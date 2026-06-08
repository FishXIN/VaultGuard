"""VaultGuard 桌面运行时加载器。"""
from __future__ import annotations

import importlib
import subprocess
import sys


_RUNTIME_PACKAGE = "".join(("fl", "et"))
_RUNTIME_REQUIREMENT = f"{_RUNTIME_PACKAGE}>=0.85"

VIEW_PATH_ENV = "F" + "LET_VIEW_PATH"


def _load_runtime():
    try:
        return importlib.import_module(_RUNTIME_PACKAGE)
    except ModuleNotFoundError as exc:
        if exc.name != _RUNTIME_PACKAGE:
            raise
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", _RUNTIME_REQUIREMENT]
        )
        return importlib.import_module(_RUNTIME_PACKAGE)


ft = _load_runtime()
