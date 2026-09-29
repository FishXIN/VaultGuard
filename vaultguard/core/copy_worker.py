"""Isolated copy worker for recovering data from an unhealthy source disk."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path

try:
    import xxhash
except ImportError:  # pragma: no cover
    xxhash = None


_prepared_parents: set[str] = set()
_PROGRESS_REPORT_BYTES = 8 * 1024 * 1024
_PROGRESS_REPORT_INTERVAL = 0.1


def _send(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def _new_hasher():
    return xxhash.xxh64() if xxhash is not None else hashlib.sha256()


def _ensure_parent(path: Path) -> None:
    """只为首次出现的目标目录执行 mkdir，减少大量小文件的元数据往返。"""
    key = os.fspath(path)
    if key in _prepared_parents:
        return
    path.mkdir(parents=True, exist_ok=True)
    _prepared_parents.add(key)


def _copy(task: dict) -> None:
    task_id = task["task_id"]
    src = Path(task["src"])
    dst = Path(task["dst"])
    tmp = Path(task["tmp"])
    chunk_size = max(64 * 1024, int(task["chunk_size"]))
    verify_hash = bool(task.get("verify_hash", False))
    copied = 0
    stage = "prepare_target"
    last_copy_reported = 0
    last_copy_reported_at = time.monotonic()

    _send({"type": "started", "task_id": task_id})
    try:
        _ensure_parent(dst.parent)
        tmp.unlink(missing_ok=True)
        source_hash = _new_hasher() if verify_hash else None
        stage = "open_files"
        with open(src, "rb", buffering=0) as fsrc, \
                open(tmp, "wb", buffering=0) as fdst:
            initial_stat = os.fstat(fsrc.fileno())
            stage = "copy_data"
            while True:
                chunk = fsrc.read(chunk_size)
                if not chunk:
                    break
                fdst.write(chunk)
                copied += len(chunk)
                if source_hash is not None:
                    source_hash.update(chunk)
                now = time.monotonic()
                if (last_copy_reported == 0
                        or copied - last_copy_reported
                        >= _PROGRESS_REPORT_BYTES
                        or now - last_copy_reported_at
                        >= _PROGRESS_REPORT_INTERVAL):
                    _send({
                        "type": "progress",
                        "task_id": task_id,
                        "bytes": copied,
                    })
                    last_copy_reported = copied
                    last_copy_reported_at = now
            stage = "flush_target"
            fdst.flush()
            os.fsync(fdst.fileno())
            stage = "stat_source"
            final_stat = os.fstat(fsrc.fileno())

        if final_stat.st_size != initial_stat.st_size or copied != final_stat.st_size:
            raise RuntimeError("source_size_changed")

        verified = False
        if source_hash is not None:
            stage = "verify_target"
            target_hash = _new_hasher()
            checked = 0
            last_verified_reported = 0
            last_verified_reported_at = time.monotonic()
            with open(tmp, "rb", buffering=0) as ftmp:
                while True:
                    chunk = ftmp.read(chunk_size)
                    if not chunk:
                        break
                    target_hash.update(chunk)
                    checked += len(chunk)
                    now = time.monotonic()
                    if (checked - last_verified_reported
                            >= _PROGRESS_REPORT_BYTES
                            or now - last_verified_reported_at
                            >= _PROGRESS_REPORT_INTERVAL):
                        _send({
                            "type": "verify_progress",
                            "task_id": task_id,
                            "bytes": checked,
                        })
                        last_verified_reported = checked
                        last_verified_reported_at = now
            if source_hash.hexdigest() != target_hash.hexdigest():
                raise RuntimeError("hash_mismatch")
            verified = True

        if tmp.stat().st_size != copied:
            raise RuntimeError("size_mismatch")
        stage = "apply_metadata"
        os.chmod(tmp, stat.S_IMODE(final_stat.st_mode))
        stage = "replace_target"
        os.replace(tmp, dst)
        stage = "set_target_time"
        os.utime(dst, ns=(final_stat.st_atime_ns, final_stat.st_mtime_ns))
        _send({
            "type": "done",
            "task_id": task_id,
            "bytes": copied,
            "verified": verified,
        })
    except BaseException as exc:
        if stage == "open_files":
            _prepared_parents.discard(os.fspath(dst.parent))
        _send({
            "type": "error",
            "task_id": task_id,
            "error": exc.__class__.__name__,
            "detail": str(exc)[:200],
            "bytes": copied,
        })


def run() -> None:
    _send({"type": "ready"})
    for line in sys.stdin:
        try:
            task = json.loads(line)
        except json.JSONDecodeError:
            continue
        if task.get("type") == "stop":
            return
        if task.get("type") == "copy":
            _copy(task)


if __name__ == "__main__":
    run()
