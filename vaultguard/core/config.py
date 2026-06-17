"""配置管理：支持从 JSON 文件加载与持久化，遵循平台数据目录规范。"""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path


# 数据目录指针文件名。该文件始终保存在「平台默认数据目录」内，
# 用于在用户把数据迁移到自定义目录后，依然能够定位真实的数据位置。
_POINTER_FILENAME = ".data_dir_pointer.json"

# 迁移时需要搬运的顶层条目（无论文件还是目录）。
# 这些是 VaultGuard 运行期会读写的全部业务数据，pointer 文件本身不在其列。
_MIGRATABLE_ENTRIES = (
    "config.json",
    "vaultguard.db",
    "vaultguard.db-wal",
    "vaultguard.db-shm",
    "vaultguard.db-journal",
    "logs",
    "error_reports",
)


def default_app_data_dir() -> Path:
    """各平台默认数据目录（不考虑环境变量与 pointer 重定向）。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(base) / "VaultGuard"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "VaultGuard"
    base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    return Path(base) / "VaultGuard"


def _pointer_path() -> Path:
    return default_app_data_dir() / _POINTER_FILENAME


def _read_pointer() -> Path | None:
    p = _pointer_path()
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        target = data.get("data_dir")
        if not target:
            return None
        path = Path(target).expanduser()
        return path
    except (json.JSONDecodeError, OSError):
        return None


def _write_pointer(target: Path | None) -> None:
    """写入或清除 pointer 文件。target 为 None 表示恢复默认目录。"""
    p = _pointer_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if target is None:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        return
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"data_dir": str(target)}, f, ensure_ascii=False, indent=2)


def app_data_dir() -> Path:
    """解析当前生效的数据目录。

    优先级：环境变量 VAULTGUARD_DATA_DIR > pointer 文件 > 平台默认目录。
    """
    override = os.environ.get("VAULTGUARD_DATA_DIR")
    if override:
        return Path(override).expanduser()
    pointer = _read_pointer()
    if pointer is not None:
        return pointer
    return default_app_data_dir()


def migrate_data_dir(src: Path, dst: Path) -> None:
    """将 src 下的业务数据整体迁移到 dst，迁移完成后清理 src 中已搬运的条目。

    - 不搬运 pointer 文件本身（pointer 始终留在默认目录）
    - 同名目录采用「合并 + 覆盖」语义；同名文件直接覆盖
    - 如果 src 与 dst 解析为同一目录则视为无操作
    """
    src = Path(src).expanduser().resolve()
    dst = Path(dst).expanduser().resolve()
    if src == dst:
        return
    dst.mkdir(parents=True, exist_ok=True)

    for name in _MIGRATABLE_ENTRIES:
        s = src / name
        if not s.exists():
            continue
        d = dst / name
        if s.is_dir():
            _merge_tree(s, d)
            shutil.rmtree(s, ignore_errors=True)
        else:
            d.parent.mkdir(parents=True, exist_ok=True)
            if d.exists():
                try:
                    d.unlink()
                except OSError:
                    pass
            shutil.move(str(s), str(d))


def _merge_tree(src: Path, dst: Path) -> None:
    """把 src 目录的内容合并进 dst，存在则覆盖。"""
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        target = dst / entry.name
        if entry.is_dir():
            _merge_tree(entry, target)
        else:
            if target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass
            shutil.copy2(entry, target)


def set_custom_data_dir(new_dir: Path, migrate: bool = True) -> Path:
    """切换数据目录。

    返回最终生效的绝对路径。当 migrate=True 时，会把当前数据目录的全部
    业务数据搬运到新目录；如果新目录就是平台默认目录，则同时清除 pointer。
    """
    new_dir = Path(new_dir).expanduser().resolve()
    new_dir.mkdir(parents=True, exist_ok=True)

    current = app_data_dir().expanduser().resolve()
    if migrate and current != new_dir:
        migrate_data_dir(current, new_dir)

    if new_dir == default_app_data_dir().expanduser().resolve():
        _write_pointer(None)
    else:
        _write_pointer(new_dir)
    return new_dir


@dataclass
class Settings:
    """软件设置，对应 PRD 设置页。"""
    mtime_tolerance: float = 2.0          # mtime 对比容差（秒）
    compare_size: bool = True             # 是否对比文件大小
    verify_hash: bool = False             # 是否做 hash 完整性校验
    delete_sync: bool = False             # 删除同步（默认关闭，安全第一）
    use_recycle: bool = True              # 删除时移入回收区而非物理删除
    exclude_patterns: list[str] = field(
        default_factory=lambda: ["*.tmp", "*.bak.tmp", "node_modules", ".DS_Store"]
    )
    chunk_size: int = 4 * 1024 * 1024     # 大文件分块大小（字节）
    retry_times: int = 2                  # 单文件错误重试次数
    autostart: bool = False               # 开机自启（登录时自动启动）
    last_source: str = ""                 # 上次使用的源目录（用于自动回填）
    last_target: str = ""                 # 上次使用的目标目录（用于自动回填）
    theme: str = "light"                  # 界面主题："light" 浅色 / "dark" 暗色

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        valid = {k: v for k, v in data.items() if k in cls.__annotations__}
        return cls(**valid)


class ConfigManager:
    """负责设置的加载与保存。"""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or app_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir / "config.json"
        self.settings = self.load()

    def load(self) -> Settings:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return Settings.from_dict(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
        return Settings()

    def save(self) -> None:
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.settings.to_dict(), f, ensure_ascii=False, indent=2)
