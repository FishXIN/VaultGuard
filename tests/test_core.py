"""核心逻辑自动化测试：断点续传、失败隔离、原子性、mtime 回写。"""
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from vaultguard.core.config import Settings
from vaultguard.core.database import Database
from vaultguard.core.executor import BackupExecutor, cleanup_temp_files
from vaultguard.core.models import TaskStatus
from vaultguard.core.scanner import compare
from vaultguard.core.service import BackupService


def setup_tree(root, files):
    for rel, content in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode())


def test_atomicity_and_mtime():
    """原子复制 + mtime 回写 + 第二次全跳过。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    setup_tree(src, {"a.txt": "aaa", "sub/b.txt": "bbb", "big.bin": os.urandom(2_000_000)})

    svc = BackupService(data)
    diff = svc.compare(str(src), str(dst))
    assert diff.new_count == 3, f"expected 3 new, got {diff.new_count}"
    tid = svc.create_task(str(src), str(dst), diff)
    prog, _ = svc.execute(tid, str(src), str(dst))
    assert prog.copied == 3 and prog.failed == 0, f"copied={prog.copied} failed={prog.failed}"

    # mtime 回写：目标 mtime == 源 mtime（容差内）
    for rel in ["a.txt", "sub/b.txt"]:
        assert abs((src/rel).stat().st_mtime - (dst/rel).stat().st_mtime) < 1.5, \
            f"mtime not preserved for {rel}"

    # 无残留临时文件
    assert list(dst.rglob("*.bak.tmp")) == [], "leftover tmp files"

    # 第二次对比应全跳过
    diff2 = svc.compare(str(src), str(dst))
    assert diff2.new_count == 0 and diff2.updated_count == 0 and diff2.skipped_count == 3, \
        f"second compare: new={diff2.new_count} upd={diff2.updated_count} skip={diff2.skipped_count}"
    svc.close()
    shutil.rmtree(d)
    print("PASS test_atomicity_and_mtime")


def test_update_detection():
    """更新检测：修改源文件后应识别为 updated。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    setup_tree(src, {"a.txt": "v1"})
    svc = BackupService(data)
    diff = svc.compare(str(src), str(dst))
    tid = svc.create_task(str(src), str(dst), diff)
    svc.execute(tid, str(src), str(dst))

    time.sleep(1.2)
    (src/"a.txt").write_text("v2-longer-content")
    diff2 = svc.compare(str(src), str(dst))
    assert diff2.updated_count == 1, f"expected 1 updated, got {diff2.updated_count}"

    # 执行更新，验证内容确实被覆盖
    tid2 = svc.create_task(str(src), str(dst), diff2)
    svc.execute(tid2, str(src), str(dst))
    assert (dst/"a.txt").read_text() == "v2-longer-content", "content not updated"
    svc.close()
    shutil.rmtree(d)
    print("PASS test_update_detection")


def test_failure_isolation():
    """失败隔离：源文件中途消失不应中断整个任务。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    setup_tree(src, {"a.txt": "a", "b.txt": "b", "c.txt": "c"})
    svc = BackupService(data)
    diff = svc.compare(str(src), str(dst))
    tid = svc.create_task(str(src), str(dst), diff)

    # 在 pending 写入后、执行前删除一个源文件 -> 制造一个失败项
    (src/"b.txt").unlink()
    prog, _ = svc.execute(tid, str(src), str(dst))
    assert prog.failed == 1, f"expected 1 failed, got {prog.failed}"
    assert prog.copied == 2, f"expected 2 copied, got {prog.copied}"
    task = svc.db.get_task(tid)
    assert task["status"] == TaskStatus.FAILED.value
    svc.close()
    shutil.rmtree(d)
    print("PASS test_failure_isolation")


def test_resume():
    """断点续传：中途取消后，续传只处理剩余文件，不重做。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    # 10 个较大文件，便于在执行中取消
    setup_tree(src, {f"f{i}.bin": os.urandom(1_000_000) for i in range(10)})
    svc = BackupService(data)
    diff = svc.compare(str(src), str(dst))
    tid = svc.create_task(str(src), str(dst), diff)

    executor = svc.make_executor()
    count = {"n": 0}

    def cb(prog):
        count["n"] = prog.processed_files
        if prog.processed_files >= 3 and not executor._cancel_event.is_set():
            executor.cancel()

    prog = executor.run(tid, str(src), str(dst), progress_cb=cb)
    assert not prog.finished, "should have been cancelled, not finished"
    task = svc.db.get_task(tid)
    assert task["status"] == TaskStatus.PAUSED.value, f"status={task['status']}"

    done_after_cancel = sum(1 for it in svc.db.get_pending_items(tid) if it["done"])
    assert 0 < done_after_cancel < 10, f"done={done_after_cancel} (expected partial)"

    # 续传
    resumable = svc.find_resumable(str(src), str(dst))
    assert resumable is not None and resumable["id"] == tid, "resumable not found"
    executor2 = svc.make_executor()
    prog2 = executor2.run(tid, str(src), str(dst), resume=True)
    assert prog2.finished, "resume should finish"
    # 全部完成
    all_done = sum(1 for it in svc.db.get_pending_items(tid) if it["done"])
    assert all_done == 10, f"after resume done={all_done}"
    # 目标文件齐全且内容正确
    for i in range(10):
        assert (dst/f"f{i}.bin").stat().st_size == 1_000_000
    svc.close()
    shutil.rmtree(d)
    print(f"PASS test_resume (cancelled after {done_after_cancel}, resumed to 10)")


def test_exclude():
    """排除规则：node_modules 与 *.tmp 应被忽略。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    setup_tree(src, {
        "keep.txt": "k", "x.tmp": "t",
        "node_modules/lib.js": "n", "deep/y.tmp": "t2",
    })
    svc = BackupService(data)
    diff = svc.compare(str(src), str(dst))
    paths = {it.rel_path for it in diff.pending_items}
    assert "keep.txt" in paths, "keep.txt should be included"
    assert not any("node_modules" in p for p in paths), "node_modules not excluded"
    assert not any(p.endswith(".tmp") for p in paths), "*.tmp not excluded"
    assert diff.new_count == 1, f"expected 1, got {diff.new_count}: {paths}"
    svc.close()
    shutil.rmtree(d)
    print("PASS test_exclude")


if __name__ == "__main__":
    test_atomicity_and_mtime()
    test_update_detection()
    test_failure_isolation()
    test_resume()
    test_exclude()
    print("\n=== ALL TESTS PASSED ===")
