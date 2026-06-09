"""模块 4：SQLite 日志与任务持久化层。

包含三张表：backup_tasks / file_logs / pending_items。
pending_items 同时承担「先选后执行」清单与「断点续传」依据（done 标志）。
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from .models import Action, DiffItem, DiffResult, TaskStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS backup_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_path TEXT,
  target_path TEXT,
  start_time INTEGER,
  end_time INTEGER,
  status TEXT,
  resume_point TEXT,
  total_files INTEGER DEFAULT 0,
  copied_files INTEGER DEFAULT 0,
  skipped_files INTEGER DEFAULT 0,
  failed_files INTEGER DEFAULT 0,
  deleted_files INTEGER DEFAULT 0,
  total_bytes INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS file_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER,
  file_path TEXT,
  action TEXT,
  reason TEXT,
  size INTEGER,
  verified INTEGER DEFAULT 0,
  timestamp INTEGER,
  FOREIGN KEY(task_id) REFERENCES backup_tasks(id)
);

CREATE TABLE IF NOT EXISTS pending_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER,
  file_path TEXT,
  action TEXT,
  size INTEGER,
  done INTEGER DEFAULT 0,
  FOREIGN KEY(task_id) REFERENCES backup_tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_pending_task ON pending_items(task_id);
CREATE INDEX IF NOT EXISTS idx_filelogs_task ON file_logs(task_id);
"""


class Database:
    """线程安全的 SQLite 封装。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """对旧版本数据库做幂等的列补齐，避免历史用户升级后报错。"""
        cur = self._conn.execute("PRAGMA table_info(backup_tasks)")
        cols = {row["name"] for row in cur.fetchall()}
        if "deleted_files" not in cols:
            self._conn.execute(
                "ALTER TABLE backup_tasks ADD COLUMN deleted_files INTEGER DEFAULT 0"
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------- 任务 ----------
    def create_task(self, source: str, target: str, diff: DiffResult) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO backup_tasks (source_path, target_path, start_time, status, "
                "total_files, skipped_files, total_bytes) VALUES (?,?,?,?,?,?,?)",
                (source, target, int(time.time()), TaskStatus.PENDING.value,
                 len(diff.pending_items), diff.skipped_count, diff.pending_bytes),
            )
            task_id = cur.lastrowid
            # 写入待备份清单（批量）
            rows = [
                (task_id, item.rel_path, item.action.value, item.size)
                for item in diff.pending_items
            ]
            self._conn.executemany(
                "INSERT INTO pending_items (task_id, file_path, action, size) VALUES (?,?,?,?)",
                rows,
            )
            self._conn.commit()
            return task_id

    def update_task_status(self, task_id: int, status: TaskStatus,
                           resume_point: Optional[str] = None) -> None:
        with self._lock:
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                self._conn.execute(
                    "UPDATE backup_tasks SET status=?, end_time=?, resume_point=? WHERE id=?",
                    (status.value, int(time.time()), resume_point, task_id),
                )
            else:
                self._conn.execute(
                    "UPDATE backup_tasks SET status=?, resume_point=? WHERE id=?",
                    (status.value, resume_point, task_id),
                )
            self._conn.commit()

    def update_task_counts(self, task_id: int, copied: int, skipped: int,
                           failed: int, deleted: int = 0) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE backup_tasks SET copied_files=?, skipped_files=?, "
                "failed_files=?, deleted_files=? WHERE id=?",
                (copied, skipped, failed, deleted, task_id),
            )
            self._conn.commit()

    def get_task(self, task_id: int) -> Optional[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM backup_tasks WHERE id=?", (task_id,))
            return cur.fetchone()

    def list_tasks(self, limit: int = 100) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM backup_tasks ORDER BY start_time DESC LIMIT ?", (limit,)
            )
            return cur.fetchall()

    def find_resumable_task(self, source: str, target: str) -> Optional[sqlite3.Row]:
        """查找同源/目标且未完成（running/paused）的任务，用于断点续传。"""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM backup_tasks WHERE source_path=? AND target_path=? "
                "AND status IN (?, ?) ORDER BY start_time DESC LIMIT 1",
                (source, target, TaskStatus.RUNNING.value, TaskStatus.PAUSED.value),
            )
            return cur.fetchone()

    # ---------- 待备份清单 / 断点续传 ----------
    def get_pending_items(self, task_id: int, only_undone: bool = False) -> list[sqlite3.Row]:
        with self._lock:
            sql = "SELECT * FROM pending_items WHERE task_id=?"
            if only_undone:
                sql += " AND done=0"
            cur = self._conn.execute(sql + " ORDER BY id", (task_id,))
            return cur.fetchall()

    def mark_item_done(self, item_id: int) -> None:
        with self._lock:
            self._conn.execute("UPDATE pending_items SET done=1 WHERE id=?", (item_id,))
            self._conn.commit()

    # ---------- 文件日志 ----------
    def add_file_log(self, task_id: int, file_path: str, action: Action,
                     reason: str, size: int, verified: bool) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO file_logs (task_id, file_path, action, reason, size, verified, timestamp) "
                "VALUES (?,?,?,?,?,?,?)",
                (task_id, file_path, action.value, reason, size,
                 1 if verified else 0, int(time.time())),
            )
            self._conn.commit()

    def get_file_logs(self, task_id: int, limit: int = 5000) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM file_logs WHERE task_id=? ORDER BY id LIMIT ?",
                (task_id, limit),
            )
            return cur.fetchall()
