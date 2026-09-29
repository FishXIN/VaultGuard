"""Isolated copy worker for recovering data from an unhealthy source disk."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import time
import urllib.request
from pathlib import Path

try:
    import xxhash
except ImportError:  # pragma: no cover
    xxhash = None


def _send(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def _new_hasher():
    return xxhash.xxh64() if xxhash is not None else hashlib.sha256()


# #region debug-point A-D:copy-failure-reporter
def _debug_report_failure(
    task: dict,
    src: Path,
    dst: Path,
    stage: str,
    exc: BaseException,
    copied: int,
) -> None:
    try:
        payload = {
            "sessionId": "two-file-copy-failures",
            "runId": os.environ.get("VAULTGUARD_DEBUG_RUN", "pre-fix"),
            "hypothesisId": "A-D",
            "location": "vaultguard/core/copy_worker.py:_copy",
            "msg": "[DEBUG] isolated copy failed",
            "data": {
                "task_id": task.get("task_id"),
                "src": str(src),
                "dst": str(dst),
                "stage": stage,
                "error": exc.__class__.__name__,
                "detail": str(exc)[:500],
                "errno": getattr(exc, "errno", None),
                "winerror": getattr(exc, "winerror", None),
                "bytes": copied,
            },
            "ts": int(time.time() * 1000),
        }
        request = urllib.request.Request(
            "http://192.168.3.51:7778/event",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(request, timeout=0.5).read()
    except Exception:
        pass
# #endregion


def _copy(task: dict) -> None:
    task_id = task["task_id"]
    src = Path(task["src"])
    dst = Path(task["dst"])
    tmp = Path(task["tmp"])
    chunk_size = max(64 * 1024, int(task["chunk_size"]))
    verify_hash = bool(task.get("verify_hash", False))
    copied = 0
    stage = "prepare_target"

    _send({"type": "started", "task_id": task_id})
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
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
                _send({
                    "type": "progress",
                    "task_id": task_id,
                    "bytes": copied,
                })
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
            with open(tmp, "rb", buffering=0) as ftmp:
                while True:
                    chunk = ftmp.read(chunk_size)
                    if not chunk:
                        break
                    target_hash.update(chunk)
                    checked += len(chunk)
                    _send({
                        "type": "verify_progress",
                        "task_id": task_id,
                        "bytes": checked,
                    })
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
        # #region debug-point A-D:copy-failure
        _debug_report_failure(task, src, dst, stage, exc, copied)
        # #endregion
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
