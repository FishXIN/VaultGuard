"""核心数据模型定义。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Action(str, Enum):
    """文件操作类型。"""
    NEW = "new"          # 新增：目标端不存在
    UPDATED = "updated"  # 更新：源端 mtime 更新或大小不同
    SKIP = "skip"        # 跳过：目标端已存在且不比源端旧
    EXTRA = "extra"      # 多余：目标端存在但源端已不存在（待删除候选）
    COPY = "copy"        # 日志：实际复制
    DELETE = "delete"    # 日志：删除多余文件
    FAIL = "fail"        # 日志：失败


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FileEntry:
    """单个文件的扫描信息。"""
    rel_path: str       # 相对源根目录的路径
    size: int           # 字节
    mtime: float        # 修改时间（秒，浮点）


@dataclass
class DiffItem:
    """对比结果中的一条待处理项。"""
    rel_path: str
    action: Action      # NEW / UPDATED / SKIP
    size: int
    src_mtime: float
    dst_mtime: Optional[float] = None
    reason: str = ""    # new / updated / unchanged


@dataclass
class DiffResult:
    """整次对比的结果汇总。"""
    new_items: list[DiffItem] = field(default_factory=list)
    updated_items: list[DiffItem] = field(default_factory=list)
    skipped_items: list[DiffItem] = field(default_factory=list)
    extra_items: list[DiffItem] = field(default_factory=list)

    @property
    def pending_items(self) -> list[DiffItem]:
        """待备份清单（新增 + 更新 + 待删除）。"""
        return self.new_items + self.updated_items + self.extra_items

    @property
    def new_count(self) -> int:
        return len(self.new_items)

    @property
    def updated_count(self) -> int:
        return len(self.updated_items)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_items)

    @property
    def extra_count(self) -> int:
        return len(self.extra_items)

    @property
    def pending_bytes(self) -> int:
        return sum(i.size for i in self.new_items + self.updated_items)


@dataclass
class CompareProgress:
    """对比过程中的实时进度快照。"""
    phase: str = "comparing"       # scanning / comparing
    current_file: str = ""
    processed_files: int = 0
    total_files: int = 0
    progress_ratio: float = 0.0
    elapsed_seconds: float = 0.0
    eta_seconds: float = 0.0
    finished: bool = False


@dataclass
class CopyProgress:
    """执行过程中的实时进度快照。"""
    current_file: str = ""
    processed_files: int = 0
    total_files: int = 0
    transferred_bytes: int = 0
    total_bytes: int = 0
    copied: int = 0
    skipped: int = 0
    deleted: int = 0
    failed: int = 0
    speed_bps: float = 0.0       # 字节/秒
    eta_seconds: float = 0.0     # 预计剩余秒数
    finished: bool = False
