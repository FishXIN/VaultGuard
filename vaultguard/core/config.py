"""配置管理：支持从 JSON 文件加载与持久化，遵循平台数据目录规范。"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path


def app_data_dir() -> Path:
    """各平台标准数据目录。"""
    # 允许通过环境变量覆盖（便于测试与自定义数据位置）
    override = os.environ.get("VAULTGUARD_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(base) / "VaultGuard"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "VaultGuard"
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        return Path(base) / "VaultGuard"


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
    last_source: str = ""                 # 上次使用的源目录（用于自动回填）
    last_target: str = ""                 # 上次使用的目标目录（用于自动回填）

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
