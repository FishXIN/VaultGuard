"""备份服务层：编排扫描、对比、任务创建、执行、续传，供 CLI 与 GUI 复用。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from .config import ConfigManager, app_data_dir
from .database import Database
from .executor import BackupExecutor, cleanup_temp_files
from .models import CompareProgress, CopyProgress, DiffResult, TaskStatus
from .scanner import compare


class BackupService:
    """对外统一入口。"""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.config = ConfigManager(data_dir)
        self.data_dir = self.config.data_dir
        self.db = Database(self.data_dir / "vaultguard.db")

    @property
    def settings(self):
        return self.config.settings

    def save_settings(self) -> None:
        self.config.save()

    def compare(
        self,
        source: str,
        target: str,
        progress_cb: Optional[Callable[[CompareProgress], None]] = None,
    ) -> DiffResult:
        """对比源与目标，返回 diff 清单（只对比不复制）。"""
        s = self.settings
        return compare(
            source, target,
            mtime_tolerance=s.mtime_tolerance,
            compare_size=s.compare_size,
            exclude_patterns=s.exclude_patterns,
            find_extras=s.delete_sync,
            progress_cb=progress_cb,
        )

    def find_resumable(self, source: str, target: str):
        """检测可续传的未完成任务。"""
        return self.db.find_resumable_task(source, target)

    def create_task(self, source: str, target: str, diff: DiffResult) -> int:
        return self.db.create_task(source, target, diff)

    def execute(
        self,
        task_id: int,
        source: str,
        target: str,
        resume: bool = False,
        progress_cb: Optional[Callable[[CopyProgress], None]] = None,
    ) -> tuple[CopyProgress, BackupExecutor]:
        """执行备份任务。返回最终进度与 executor（便于外部控制暂停/取消）。"""
        # 执行前清理残留临时文件（断电安全）
        cleanup_temp_files(target)
        executor = BackupExecutor(self.db, self.settings)
        prog = executor.run(task_id, source, target, resume=resume, progress_cb=progress_cb)
        # 输出文本日志
        self._write_text_log(task_id, source, target, prog)
        return prog, executor

    def make_executor(self) -> BackupExecutor:
        return BackupExecutor(self.db, self.settings)

    def _write_text_log(self, task_id: int, source: str, target: str,
                        prog: CopyProgress) -> None:
        """输出可读文本日志，便于人工排查。"""
        log_dir = self.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"task_{task_id}.log"
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] 任务 #{task_id}\n")
            f.write(f"  源: {source}\n  目标: {target}\n")
            f.write(f"  复制 {prog.copied} / 跳过 {prog.skipped} / "
                    f"删除 {prog.deleted} / 失败 {prog.failed}"
                    f"（共 {prog.total_files} 个待处理项）\n")
            f.write(f"  传输 {prog.transferred_bytes} 字节\n\n")

    def list_tasks(self, limit: int = 100):
        return self.db.list_tasks(limit)

    def get_file_logs(self, task_id: int):
        return self.db.get_file_logs(task_id)

    def close(self) -> None:
        self.db.close()
