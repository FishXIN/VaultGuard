"""模块 2 + 3：备份执行引擎（原子复制 + 完整性校验 + mtime 回写 + 断点续传）。

文件安全核心：
  - 写入原子性：先写 .bak.tmp，校验通过后原子 rename。
  - 覆盖前不破坏旧文件（临时文件机制天然满足）。
  - 完整性校验：大小校验，可选 hash。
  - 失败隔离：单文件失败不中断任务。
  - 删除同步：开启 ``delete_sync`` 时，目标端多余文件按设置走回收站或物理删除；
    回收站失败自动降级，确保用户数据可追溯。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .config import Settings
from .database import Database
from .models import Action, CopyProgress, TaskStatus

try:
    import xxhash
    _HAS_XXHASH = True
except ImportError:  # pragma: no cover
    _HAS_XXHASH = False
    import hashlib


def _hash_file(path: str | Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    """计算文件 hash（优先 xxHash，回退 SHA-256）。"""
    if _HAS_XXHASH:
        h = xxhash.xxh64()
    else:
        h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


class BackupExecutor:
    """执行一次备份任务，支持暂停/取消/续传与实时进度回调。"""

    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self._pause_event = threading.Event()
        self._cancel_event = threading.Event()
        self._pause_event.set()  # set = 运行中

    # ---------- 控制 ----------
    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    def cancel(self) -> None:
        self._cancel_event.set()
        self._pause_event.set()  # 解除暂停以便退出

    @property
    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    # ---------- 单文件原子复制 ----------
    def _copy_one(self, src: Path, dst: Path) -> tuple[bool, bool, str]:
        """原子复制单个文件。返回 (成功, 已校验, 原因)。"""
        tmp = dst.with_name(dst.name + ".bak.tmp")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            # 清理可能残留的旧临时文件（断电安全）
            if tmp.exists():
                tmp.unlink()

            # 分块复制到临时文件
            with open(src, "rb") as fsrc, open(tmp, "wb") as fdst:
                shutil.copyfileobj(fsrc, fdst, self.settings.chunk_size)
                fdst.flush()
                os.fsync(fdst.fileno())

            # 完整性校验：大小
            src_size = src.stat().st_size
            if tmp.stat().st_size != src_size:
                tmp.unlink(missing_ok=True)
                return False, False, "error_size_mismatch"

            verified = False
            # 可选 hash 校验
            if self.settings.verify_hash:
                if _hash_file(src, self.settings.chunk_size) != _hash_file(tmp, self.settings.chunk_size):
                    tmp.unlink(missing_ok=True)
                    return False, False, "error_hash_mismatch"
                verified = True

            # 保留权限
            try:
                shutil.copymode(src, tmp)
            except OSError:
                pass

            # 原子重命名覆盖目标
            os.replace(tmp, dst)

            # 回写源 mtime 到目标端（增量备份成败关键）
            src_st = src.stat()
            os.utime(dst, (src_st.st_atime, src_st.st_mtime))

            return True, verified, "ok"
        except OSError as e:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            return False, False, f"error_io:{e.__class__.__name__}"

    def _copy_with_retry(self, src: Path, dst: Path) -> tuple[bool, bool, str]:
        attempts = self.settings.retry_times + 1
        last = (False, False, "error_unknown")
        for i in range(attempts):
            ok, verified, reason = self._copy_one(src, dst)
            if ok:
                return ok, verified, reason
            last = (ok, verified, reason)
            time.sleep(0.1 * (i + 1))
        return last

    # ---------- 单文件删除（多余文件回收 / 物理删除） ----------
    def _delete_one(self, dst: Path) -> tuple[bool, str]:
        """按设置删除单个目标文件。

        - 默认（``use_recycle=True``）尝试调用系统回收站。
          macOS 借助 AppleScript 把文件移入"废纸篓"，失败时降级为物理删除。
        - ``use_recycle=False`` 直接物理删除。
        - 文件不存在视作删除成功（幂等）。
        """
        if not dst.exists():
            return True, "ok_missing"

        if not self.settings.use_recycle:
            try:
                dst.unlink()
                return True, "ok_unlink"
            except OSError as e:
                return False, f"error_unlink:{e.__class__.__name__}"

        if sys.platform == "darwin":
            script = (
                'tell application "Finder" to delete (POSIX file '
                f'"{str(dst).replace(chr(34), chr(92) + chr(34))}" as alias)'
            )
            try:
                subprocess.run(
                    ["osascript", "-e", script],
                    check=True,
                    timeout=10,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True, "ok_recycle"
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                    FileNotFoundError):
                pass  # 降级为物理删除
        # Linux / Windows / 兜底：尝试 send2trash，缺失时物理删除
        try:
            import send2trash  # type: ignore
            send2trash.send2trash(str(dst))
            return True, "ok_recycle"
        except Exception:  # noqa: BLE001
            try:
                dst.unlink()
                return True, "ok_unlink_fallback"
            except OSError as e:
                return False, f"error_unlink:{e.__class__.__name__}"

    # ---------- 任务执行 ----------
    def run(
        self,
        task_id: int,
        source: str | Path,
        target: str | Path,
        resume: bool = False,
        progress_cb: Optional[Callable[[CopyProgress], None]] = None,
    ) -> CopyProgress:
        """执行任务。resume=True 时只处理 done=0 的项（断点续传）。"""
        source = Path(source)
        target = Path(target)
        self._cancel_event.clear()
        self._pause_event.set()

        items = self.db.get_pending_items(task_id, only_undone=resume)
        all_items = self.db.get_pending_items(task_id, only_undone=False)
        already_done = sum(1 for it in all_items if it["done"])
        # 已完成项里区分"复制成功"与"删除成功"，恢复时不丢失统计
        already_copied = sum(
            1 for it in all_items
            if it["done"] and it["action"] != Action.EXTRA.value)
        already_deleted = sum(
            1 for it in all_items
            if it["done"] and it["action"] == Action.EXTRA.value)

        total_files = len(all_items)
        total_bytes = sum(it["size"] for it in all_items
                          if it["action"] != Action.EXTRA.value)
        done_bytes = sum(
            it["size"] for it in all_items
            if it["done"] and it["action"] != Action.EXTRA.value)

        prog = CopyProgress(
            total_files=total_files,
            total_bytes=total_bytes,
            processed_files=already_done,
            transferred_bytes=done_bytes,
            copied=already_copied,
            deleted=already_deleted,
        )

        self.db.update_task_status(task_id, TaskStatus.RUNNING)
        start = time.time()
        bytes_this_run = 0

        for it in items:
            # 暂停处理
            self._pause_event.wait()
            # 取消处理
            if self._cancel_event.is_set():
                self.db.update_task_status(
                    task_id, TaskStatus.PAUSED,
                    resume_point=f"{prog.processed_files}/{total_files}",
                )
                self.db.update_task_counts(
                    task_id, prog.copied, prog.skipped, prog.failed,
                    prog.deleted)
                return prog

            rel = it["file_path"]
            src_file = source / rel
            dst_file = target / rel
            prog.current_file = rel
            is_delete = it["action"] == Action.EXTRA.value

            if is_delete:
                ok, reason = self._delete_one(dst_file)
                if ok:
                    prog.deleted += 1
                    self.db.mark_item_done(it["id"])
                    self.db.add_file_log(task_id, rel, Action.DELETE, reason,
                                         it["size"], False)
                else:
                    prog.failed += 1
                    self.db.add_file_log(task_id, rel, Action.FAIL, reason,
                                         it["size"], False)
                prog.processed_files += 1
            elif not src_file.exists():
                # 源文件已不存在，记录失败但不中断
                prog.failed += 1
                self.db.add_file_log(task_id, rel, Action.FAIL, "error_src_missing",
                                     it["size"], False)
                prog.processed_files += 1
                prog.transferred_bytes += it["size"]
                bytes_this_run += it["size"]
            else:
                ok, verified, reason = self._copy_with_retry(src_file, dst_file)
                if ok:
                    prog.copied += 1
                    self.db.mark_item_done(it["id"])
                    self.db.add_file_log(task_id, rel, Action.COPY, it["action"],
                                         it["size"], verified)
                else:
                    prog.failed += 1
                    self.db.add_file_log(task_id, rel, Action.FAIL, reason,
                                         it["size"], False)
                prog.processed_files += 1
                prog.transferred_bytes += it["size"]
                bytes_this_run += it["size"]

            elapsed = time.time() - start
            if elapsed > 0 and total_bytes > 0:
                prog.speed_bps = bytes_this_run / elapsed
                remaining = total_bytes - prog.transferred_bytes
                prog.eta_seconds = remaining / prog.speed_bps if prog.speed_bps > 0 else 0

            if progress_cb:
                progress_cb(prog)

        # 收尾
        prog.finished = True
        final_status = TaskStatus.COMPLETED if prog.failed == 0 else TaskStatus.FAILED
        self.db.update_task_counts(
            task_id, prog.copied, prog.skipped, prog.failed, prog.deleted)
        self.db.update_task_status(task_id, final_status,
                                   resume_point=f"{prog.processed_files}/{total_files}")
        if progress_cb:
            progress_cb(prog)
        return prog


def cleanup_temp_files(target: str | Path) -> int:
    """清理目标目录下残留的 .bak.tmp 文件（断电/崩溃安全）。返回清理数量。"""
    target = Path(target)
    count = 0
    if not target.exists():
        return 0
    for p in target.rglob("*.bak.tmp"):
        try:
            p.unlink()
            count += 1
        except OSError:
            pass
    return count
