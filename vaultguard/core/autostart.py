"""开机自启管理：在登录时自动启动 VaultGuard。

macOS 采用用户级 LaunchAgent（~/Library/LaunchAgents/*.plist），
Windows 采用当前用户的注册表 Run 键。两者均无需管理员权限。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 启动项的唯一标识（macOS plist Label / Windows 注册表值名）。
_LABEL = "com.vaultguard.app"
_WIN_VALUE_NAME = "VaultGuard"
_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command() -> list[str]:
    """计算用于开机启动的命令行参数。"""
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            # sys.executable 形如 .../备份了嘛.app/Contents/MacOS/VaultGuard，
            # 自启交给系统用 open 打开 .app 包，确保以正常 GUI 应用方式启动。
            exe = Path(sys.executable).resolve()
            app_bundle = exe.parents[2]
            if app_bundle.suffix == ".app":
                return ["/usr/bin/open", str(app_bundle)]
            return [str(exe)]
        return [sys.executable]
    # 开发模式：用当前 Python 解释器运行项目入口 main.py。
    main_py = Path(__file__).resolve().parents[2] / "main.py"
    return [sys.executable, str(main_py)]


# ---------------- macOS ----------------

def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def _macos_enable() -> None:
    args = _launch_command()
    program_args = "".join(
        f"        <string>{a}</string>\n" for a in args
    )
    plist = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>{_LABEL}</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"{program_args}"
        "    </array>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "</dict>\n"
        "</plist>\n"
    )
    path = _macos_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plist, encoding="utf-8")


def _macos_disable() -> None:
    try:
        _macos_plist_path().unlink()
    except FileNotFoundError:
        pass


def _macos_is_enabled() -> bool:
    return _macos_plist_path().exists()


# ---------------- Windows ----------------

def _win_run_key():
    import winreg  # noqa: PLC0415  仅 Windows 可用

    return winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0,
        winreg.KEY_READ | winreg.KEY_WRITE)


def _win_command_str() -> str:
    args = _launch_command()
    return " ".join(f'"{a}"' if " " in a else a for a in args)


def _win_enable() -> None:
    import winreg  # noqa: PLC0415

    with _win_run_key() as key:
        winreg.SetValueEx(
            key, _WIN_VALUE_NAME, 0, winreg.REG_SZ, _win_command_str())


def _win_disable() -> None:
    import winreg  # noqa: PLC0415

    try:
        with _win_run_key() as key:
            winreg.DeleteValue(key, _WIN_VALUE_NAME)
    except FileNotFoundError:
        pass


def _win_is_enabled() -> bool:
    import winreg  # noqa: PLC0415

    try:
        with _win_run_key() as key:
            winreg.QueryValueEx(key, _WIN_VALUE_NAME)
            return True
    except FileNotFoundError:
        return False


# ---------------- 对外统一接口 ----------------

def is_supported() -> bool:
    """当前平台是否支持开机自启管理。"""
    return sys.platform in ("darwin", "win32")


def is_enabled() -> bool:
    """查询系统中是否已登记开机自启。"""
    if sys.platform == "darwin":
        return _macos_is_enabled()
    if sys.platform == "win32":
        return _win_is_enabled()
    return False


def set_enabled(enabled: bool) -> None:
    """登记或取消开机自启。失败时抛出异常，由调用方处理。"""
    if sys.platform == "darwin":
        _macos_enable() if enabled else _macos_disable()
    elif sys.platform == "win32":
        _win_enable() if enabled else _win_disable()
