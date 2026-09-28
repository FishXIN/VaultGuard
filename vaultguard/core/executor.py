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

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .config import Settings
from .database import Database
from .disk_health import DiskHealth, check_backup_disks, format_health_summary
from .models import Action, CopyProgress, TaskStatus

try:
    import xxhash
    _HAS_XXHASH = True
except ImportError:  # pragma: no cover
    _HAS_XXHASH = False
    import hashlib


class _CopyControl(Exception):
    pass


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
        self.disk_health_reports: list[DiskHealth] = []
        self._pause_event = threading.Event()
        self._cancel_event = threading.Event()
        self._pause_event.set()  # set = 运行中
        self._rescue_mode = False
        self._isolated_copy = True
        self._copy_worker = None
        self._copy_worker_events = None
        self._copy_worker_seq = 0

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

    def _start_copy_worker(self):
        proc = self._copy_worker
        if proc is not None and proc.poll() is None:
            return proc, self._copy_worker_events

        env = os.environ.copy()
        env["VAULTGUARD_COPY_WORKER"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env.pop("VAULTGUARD_DIR_PICKER", None)
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.append(str(Path(__file__).resolve().parents[2] / "main.py"))

        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=env,
            creationflags=creationflags,
        )
        events: queue.Queue = queue.Queue()

        def read_events() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                try:
                    events.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
            events.put({"type": "eof"})

        threading.Thread(target=read_events, daemon=True).start()
        self._copy_worker = proc
        self._copy_worker_events = events
        return proc, events

    def _stop_copy_worker(self, force: bool = False) -> None:
        proc = self._copy_worker
        self._copy_worker = None
        self._copy_worker_events = None
        if proc is None:
            return
        try:
            if not force and proc.poll() is None and proc.stdin is not None:
                proc.stdin.write('{"type":"stop"}\n')
                proc.stdin.flush()
                proc.wait(timeout=0.5)
                return
        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
            pass
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=0.5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    proc.kill()
                except OSError:
                    pass

    @staticmethod
    def _cleanup_partial(tmp: Path) -> None:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass

    def _copy_one_rescue(
        self,
        src: Path,
        dst: Path,
        progress_cb: Optional[Callable[[int, float], None]] = None,
    ) -> tuple[bool, bool, str]:
        tmp = dst.with_name(dst.name + ".bak.tmp")
        try:
            proc, events = self._start_copy_worker()
            self._copy_worker_seq += 1
            task_id = self._copy_worker_seq
            task = {
                "type": "copy",
                "task_id": task_id,
                "src": str(src),
                "dst": str(dst),
                "tmp": str(tmp),
                "chunk_size": min(self.settings.chunk_size, 1024 * 1024),
                "verify_hash": self.settings.verify_hash,
            }
            if proc.stdin is None:
                raise OSError("copy worker stdin is unavailable")
            proc.stdin.write(json.dumps(task) + "\n")
            proc.stdin.flush()

            timeout = max(0.1, float(self.settings.rescue_stall_timeout))
            last_activity = time.monotonic()
            last_copied = 0
            while True:
                if self._cancel_event.is_set():
                    self._stop_copy_worker(force=True)
                    self._cleanup_partial(tmp)
                    return False, False, "cancelled"
                if not self._pause_event.is_set():
                    self._stop_copy_worker(force=True)
                    self._cleanup_partial(tmp)
                    return False, False, "paused"

                idle = time.monotonic() - last_activity
                if idle >= timeout:
                    self._stop_copy_worker(force=True)
                    self._cleanup_partial(tmp)
                    return False, False, "error_stalled"
                try:
                    event = events.get(timeout=min(0.2, timeout - idle))
                except queue.Empty:
                    if progress_cb:
                        progress_cb(last_copied, time.monotonic() - last_activity)
                    if proc.poll() is not None:
                        self._stop_copy_worker(force=True)
                        self._cleanup_partial(tmp)
                        return False, False, "error_worker_exited"
                    continue

                if event.get("task_id") not in (None, task_id):
                    continue
                event_type = event.get("type")
                if event_type in ("started", "progress", "verify_progress"):
                    last_activity = time.monotonic()
                    if event_type == "progress":
                        last_copied = int(event.get("bytes", 0))
                        if progress_cb:
                            progress_cb(last_copied, 0.0)
                    continue
                if event_type == "done":
                    copied = int(event.get("bytes", 0))
                    if progress_cb:
                        progress_cb(copied, 0.0)
                    return True, bool(event.get("verified", False)), "ok"
                if event_type == "error":
                    self._cleanup_partial(tmp)
                    detail = str(event.get("detail", ""))
                    if detail == "hash_mismatch":
                        return False, False, "error_hash_mismatch"
                    if detail == "source_size_changed":
                        return False, False, "error_size_mismatch"
                    if detail == "size_mismatch":
                        return False, False, "error_size_mismatch"
                    return (
                        False,
                        False,
                        f"error_io:{event.get('error', 'WorkerError')}",
                    )
                if event_type == "eof":
                    self._stop_copy_worker(force=True)
                    self._cleanup_partial(tmp)
                    return False, False, "error_worker_exited"
        except (OSError, ValueError, subprocess.SubprocessError):
            self._stop_copy_worker(force=True)
            self._cleanup_partial(tmp)
            return False, False, "error_worker_start"

    # ---------- 单文件原子复制 ----------
    def _copy_one(
        self,
        src: Path,
        dst: Path,
        progress_cb: Optional[Callable[[int, float], None]] = None,
    ) -> tuple[bool, bool, str]:
        """原子复制单个文件。返回 (成功, 已校验, 原因)。"""
        tmp = dst.with_name(dst.name + ".bak.tmp")
        if self._isolated_copy:
            return self._copy_one_rescue(src, dst, progress_cb)

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            # 清理可能残留的旧临时文件（断电安全）
            if tmp.exists():
                tmp.unlink()

            # 分块复制到临时文件，并在块边界响应暂停/取消。
            with open(src, "rb") as fsrc, open(tmp, "wb") as fdst:
                copied = 0
                chunk_size = max(64 * 1024, self.settings.chunk_size)
                while True:
                    self._pause_event.wait()
                    if self._cancel_event.is_set():
                        raise _CopyControl("cancelled")
                    chunk = fsrc.read(chunk_size)
                    if not chunk:
                        break
                    written = fdst.write(chunk)
                    if written != len(chunk):
                        raise OSError("short write")
                    copied += written
                    if progress_cb:
                        progress_cb(copied, 0.0)
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
        except _CopyControl as exc:
            self._cleanup_partial(tmp)
            return False, False, str(exc)
        except OSError as e:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            return False, False, f"error_io:{e.__class__.__name__}"

    def _copy_with_retry(
        self,
        src: Path,
        dst: Path,
        progress_cb: Optional[Callable[[int, float], None]] = None,
    ) -> tuple[bool, bool, str]:
        attempts = self.settings.retry_times + 1
        last = (False, False, "error_unknown")
        attempt = 0
        while attempt < attempts:
            ok, verified, reason = self._copy_one(src, dst, progress_cb)
            if ok:
                return ok, verified, reason
            last = (ok, verified, reason)
            if reason == "paused":
                self._pause_event.wait()
                if self._cancel_event.is_set():
                    return False, False, "cancelled"
                continue
            if reason in ("cancelled", "error_stalled"):
                return last
            if reason.startswith("error_io:") and not self._rescue_mode:
                self._rescue_mode = True
            attempt += 1
            time.sleep(0.1 * attempt)
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
        health_cb: Optional[Callable[[list[DiskHealth]], None]] = None,
    ) -> CopyProgress:
        """执行任务。resume=True 时只处理 done=0 的项（断点续传）。"""
        source = Path(source)
        target = Path(target)
        self._cancel_event.clear()
        self._pause_event.set()

        self.disk_health_reports = check_backup_disks(source, target)
        if health_cb:
            health_cb(self.disk_health_reports)
        unsafe_target = next(
            (
                report for report in self.disk_health_reports
                if report.role == "target"
                and (report.status == "failing" or report.read_only)
            ),
            None,
        )
        if unsafe_target:
            self.db.update_task_status(task_id, TaskStatus.FAILED)
            raise RuntimeError(
                "目标硬盘健康检查未通过，已停止备份："
                f"{format_health_summary(self.disk_health_reports)}"
            )

        source_health = next(
            (report for report in self.disk_health_reports
             if report.role == "source"),
            None,
        )
        self._rescue_mode = bool(
            source_health is None or source_health.status != "healthy")

        items = self.db.get_pending_items(task_id, only_undone=resume)
        if self._rescue_mode:
            # 异常源盘优先抢救小文件，并把删除操作放到最后。
            items.sort(key=lambda item: (
                item["action"] == Action.EXTRA.value,
                item["size"],
                item["id"],
            ))
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
            file_timeout_seconds=float(self.settings.rescue_stall_timeout),
            rescue_mode=self._rescue_mode,
        )

        self.db.update_task_status(task_id, TaskStatus.RUNNING)
        start = time.time()
        bytes_this_run = 0

        def emit_progress() -> None:
            elapsed = time.time() - start
            if elapsed > 0 and total_bytes > 0:
                prog.speed_bps = bytes_this_run / elapsed
                remaining = max(total_bytes - prog.transferred_bytes, 0)
                prog.eta_seconds = (
                    remaining / prog.speed_bps if prog.speed_bps > 0 else 0)
            if progress_cb:
                progress_cb(prog)

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
                self._stop_copy_worker(force=True)
                return prog

            rel = it["file_path"]
            src_file = source / rel
            dst_file = target / rel
            prog.current_file = rel
            prog.current_file_bytes = 0
            prog.current_file_size = it["size"]
            prog.file_idle_seconds = 0.0
            is_delete = it["action"] == Action.EXTRA.value

            if is_delete and self._rescue_mode:
                # 源盘异常时不依据可能不完整的扫描结果删除目标文件。
                reason = "skipped_rescue_mode"
                prog.skipped += 1
                self.db.mark_item_done(it["id"])
                self.db.add_file_log(
                    task_id, rel, Action.SKIP, reason, it["size"], False)
                prog.processed_files += 1
            elif is_delete:
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
            elif not self._isolated_copy and not src_file.exists():
                # 源文件已不存在，记录失败但不中断
                prog.failed += 1
                self.db.add_file_log(task_id, rel, Action.FAIL, "error_src_missing",
                                     it["size"], False)
                prog.processed_files += 1
                prog.transferred_bytes += it["size"]
                bytes_this_run += it["size"]
            else:
                file_reported_bytes = 0

                def file_progress(
                    copied_bytes: int,
                    idle_seconds: float = 0.0,
                ) -> None:
                    nonlocal file_reported_bytes, bytes_this_run
                    bounded = min(max(copied_bytes, 0), it["size"])
                    if bounded > file_reported_bytes:
                        delta = bounded - file_reported_bytes
                        file_reported_bytes = bounded
                        prog.transferred_bytes += delta
                        bytes_this_run += delta
                    prog.current_file_bytes = bounded
                    prog.file_idle_seconds = max(idle_seconds, 0.0)
                    emit_progress()

                ok, verified, reason = self._copy_with_retry(
                    src_file, dst_file, file_progress)
                if reason == "cancelled":
                    self.db.update_task_status(
                        task_id, TaskStatus.PAUSED,
                        resume_point=f"{prog.processed_files}/{total_files}",
                    )
                    self.db.update_task_counts(
                        task_id, prog.copied, prog.skipped, prog.failed,
                        prog.deleted)
                    self._stop_copy_worker(force=True)
                    return prog
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
                remaining_bytes = max(it["size"] - file_reported_bytes, 0)
                prog.transferred_bytes += remaining_bytes
                bytes_this_run += remaining_bytes
                prog.current_file_bytes = it["size"]
                prog.file_idle_seconds = 0.0

            emit_progress()

        # 收尾
        self._stop_copy_worker()
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
