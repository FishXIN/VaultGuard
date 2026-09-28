"""核心逻辑自动化测试：断点续传、失败隔离、原子性、mtime 回写。"""
import os
import plistlib
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from vaultguard.core import disk_health
from vaultguard.core.config import Settings
from vaultguard.core.database import Database
from vaultguard.core.disk_health import DiskHealth, check_disk_health
from vaultguard.core.executor import (
    BackupExecutor,
    TaskAlreadyRunningError,
    cleanup_temp_files,
)
from vaultguard.core.models import Action, DiffItem, DiffResult, TaskStatus
from vaultguard.core.scanner import compare, scan_directory
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


def test_scan_progress_is_continuous():
    """大目录扫描保持连续进度，但不能为每个文件制造一次回调。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    src.mkdir(parents=True)
    dst.mkdir(parents=True)
    setup_tree(src, {f"f{i}.txt": "x" for i in range(260)})

    events = []
    svc = BackupService(data)
    with patch("vaultguard.core.scanner.scan_directory",
               wraps=scan_directory) as scan:
        diff = svc.compare(str(src), str(dst), progress_cb=events.append)
    scan_ratios = [
        round(e.progress_ratio, 4)
        for e in events
        if e.phase == "scanning" and 0 < e.progress_ratio < 1
    ]
    unique_ratios = sorted(set(scan_ratios))
    current_files = [
        e.current_file for e in events
        if e.phase == "scanning" and e.current_file
    ]
    assert diff.new_count == 260, f"expected 260, got {diff.new_count}"
    assert len(unique_ratios) >= 5, f"scan progress jumped: {unique_ratios}"
    assert unique_ratios == sorted(unique_ratios), "scan progress should be monotonic"
    assert 5 <= len(current_files) < 50, \
        f"scan callbacks should be sampled, got {len(current_files)}"
    assert all(name.endswith(".txt") for name in current_files), current_files[:5]
    assert scan.call_count == 1, f"source should be scanned once, got {scan.call_count}"

    svc.close()
    shutil.rmtree(d)
    print("PASS test_scan_progress_is_continuous")


def test_macos_health_check_is_read_only():
    """磁盘健康检查只读取系统元数据，不启动自检、修复或写入操作。"""
    d = tempfile.mkdtemp()
    df_result = subprocess.CompletedProcess(
        ["df"], 0,
        stdout=(
            "Filesystem 512-blocks Used Available Capacity Mounted on\n"
            "/dev/disk9s1 1000 100 900 10% /Volumes/Test\n"
        ),
        stderr="",
    )
    diskutil_result = subprocess.CompletedProcess(
        ["diskutil"], 0,
        stdout=plistlib.dumps({
            "DeviceNode": "/dev/disk9s1",
            "VolumeName": "Test",
            "SMARTStatus": "Verified",
            "WritableVolume": True,
        }),
        stderr=b"",
    )

    with patch("vaultguard.core.disk_health.sys.platform", "darwin"), \
            patch("vaultguard.core.disk_health.subprocess.run",
                  side_effect=[df_result, diskutil_result]) as run:
        report = check_disk_health(d, "target")

    commands = [" ".join(call.args[0]) for call in run.call_args_list]
    assert report.status == "healthy", report
    assert commands == [
        f"df -P {Path(d).resolve()}",
        "diskutil info -plist /dev/disk9s1",
    ], commands
    forbidden = ("verifyDisk", "repair", "smartctl", "badblocks", "fsck")
    assert not any(word in " ".join(commands) for word in forbidden)
    shutil.rmtree(d)
    print("PASS test_macos_health_check_is_read_only")


def test_failing_target_health_blocks_backup():
    """目标盘明确报告故障时，不应开始创建或覆盖目标文件。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    setup_tree(src, {"a.txt": "safe"})
    setup_tree(dst, {"leftover.bak.tmp": "must remain untouched"})
    svc = BackupService(data)
    diff = svc.compare(str(src), str(dst))
    tid = svc.create_task(str(src), str(dst), diff)
    reports = [
        DiskHealth("source", str(src), "healthy", smart_status="Verified"),
        DiskHealth("target", str(dst), "failing", smart_status="Failing"),
    ]

    with patch("vaultguard.core.executor.check_backup_disks",
               return_value=reports):
        try:
            svc.execute(tid, str(src), str(dst))
            raise AssertionError("backup should stop for a failing target disk")
        except RuntimeError as exc:
            assert "目标硬盘健康检查未通过" in str(exc)

    assert not (dst/"a.txt").exists()
    assert (dst/"leftover.bak.tmp").exists()
    assert svc.db.get_task(tid)["status"] == TaskStatus.FAILED.value
    svc.close()
    shutil.rmtree(d)
    print("PASS test_failing_target_health_blocks_backup")


def test_health_check_timeout_is_bounded():
    """健康检查子进程无响应时，主任务必须按时返回保守状态。"""
    class HungProcess:
        returncode = None

        def communicate(self, _input, timeout):
            raise subprocess.TimeoutExpired("health-worker", timeout)

        def kill(self):
            self.returncode = -9

    process = HungProcess()
    with patch("vaultguard.core.disk_health.subprocess.Popen",
               return_value=process):
        report = disk_health._check_disk_health_bounded(
            "/possibly-damaged", "source", timeout=0.01)

    assert process.returncode == -9
    assert report.status == "warning"
    assert "exceeded" in report.detail
    print("PASS test_health_check_timeout_is_bounded")


def test_cancel_inside_large_file():
    """取消应在分块边界生效，不必等待整个大文件复制完成。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    setup_tree(src, {"large.bin": os.urandom(2_000_000)})
    svc = BackupService(data)
    svc.settings.chunk_size = 64 * 1024
    diff = svc.compare(str(src), str(dst))
    tid = svc.create_task(str(src), str(dst), diff)
    executor = svc.make_executor()
    reports = [
        DiskHealth("source", str(src), "healthy", smart_status="Verified"),
        DiskHealth("target", str(dst), "healthy", smart_status="Verified"),
    ]

    def cancel_after_first_chunk(prog):
        if prog.transferred_bytes > 0 and prog.processed_files == 0:
            executor.cancel()

    with patch("vaultguard.core.executor.check_backup_disks",
               return_value=reports):
        prog = executor.run(
            tid, str(src), str(dst), progress_cb=cancel_after_first_chunk)

    assert not prog.finished
    assert prog.processed_files == 0
    assert svc.db.get_task(tid)["status"] == TaskStatus.PAUSED.value
    assert not (dst/"large.bin").exists()
    assert not (dst/"large.bin.bak.tmp").exists()
    svc.close()
    shutil.rmtree(d)
    print("PASS test_cancel_inside_large_file")


def test_isolated_hash_verification():
    """隔离复制进程仍应执行可选 hash 校验并记录 verified。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    setup_tree(src, {"checked.bin": os.urandom(512_000)})
    svc = BackupService(data)
    svc.settings.verify_hash = True
    diff = svc.compare(str(src), str(dst))
    tid = svc.create_task(str(src), str(dst), diff)
    reports = [
        DiskHealth("source", str(src), "healthy", smart_status="Verified"),
        DiskHealth("target", str(dst), "healthy", smart_status="Verified"),
    ]

    with patch("vaultguard.core.executor.check_backup_disks",
               return_value=reports):
        prog, _ = svc.execute(tid, str(src), str(dst))

    logs = svc.get_file_logs(tid)
    assert prog.copied == 1 and prog.failed == 0
    assert logs[0]["verified"] == 1
    assert (src/"checked.bin").read_bytes() == (dst/"checked.bin").read_bytes()
    svc.close()
    shutil.rmtree(d)
    print("PASS test_isolated_hash_verification")


def test_rescue_stall_skips_and_continues():
    """异常源盘的单文件无进展超时后，应继续抢救后续可读文件。"""
    if not hasattr(os, "mkfifo"):
        print("PASS test_rescue_stall_skips_and_continues (unsupported)")
        return

    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    src.mkdir(parents=True)
    os.mkfifo(src/"stuck.pipe")
    setup_tree(src, {"readable.txt": "recover me"})
    diff = DiffResult(new_items=[
        DiffItem("stuck.pipe", Action.NEW, 0, 0.0),
        DiffItem("readable.txt", Action.NEW, 10, 0.0),
    ])
    svc = BackupService(data)
    svc.settings.rescue_stall_timeout = 0.4
    svc.settings.retry_times = 0
    tid = svc.create_task(str(src), str(dst), diff)
    reports = [
        DiskHealth("source", str(src), "failing", smart_status="Failing"),
        DiskHealth("target", str(dst), "healthy", smart_status="Verified"),
    ]

    started = time.monotonic()
    with patch("vaultguard.core.executor.check_backup_disks",
               return_value=reports):
        prog, _ = svc.execute(tid, str(src), str(dst))
    elapsed = time.monotonic() - started

    assert elapsed < 5, elapsed
    assert prog.failed == 1 and prog.copied == 1, prog
    assert (dst/"readable.txt").read_text() == "recover me"
    assert not (dst/"stuck.pipe").exists()
    assert not list(dst.rglob("*.bak.tmp"))
    svc.close()
    shutil.rmtree(d)
    print("PASS test_rescue_stall_skips_and_continues")


def test_rescue_mode_never_deletes_target_files():
    """源盘异常时，可能漏扫文件，因此删除同步必须自动降级为保留。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    src.mkdir(parents=True)
    setup_tree(dst, {"keep-on-target.txt": "only copy"})
    diff = DiffResult(extra_items=[
        DiffItem("keep-on-target.txt", Action.EXTRA, 9, 0.0),
    ])
    svc = BackupService(data)
    tid = svc.create_task(str(src), str(dst), diff)
    reports = [
        DiskHealth("source", str(src), "unknown", smart_status="Not Supported"),
        DiskHealth("target", str(dst), "healthy", smart_status="Verified"),
    ]

    with patch("vaultguard.core.executor.check_backup_disks",
               return_value=reports):
        prog, _ = svc.execute(tid, str(src), str(dst))

    assert prog.deleted == 0 and prog.skipped == 1
    assert (dst/"keep-on-target.txt").read_text() == "only copy"
    svc.close()
    shutil.rmtree(d)
    print("PASS test_rescue_mode_never_deletes_target_files")


def test_duplicate_task_execution_is_rejected():
    """同一 task_id 并发启动时只允许一个执行器进入业务流程。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    setup_tree(src, {"a.txt": "a"})
    svc = BackupService(data)
    diff = svc.compare(str(src), str(dst))
    tid = svc.create_task(str(src), str(dst), diff)
    first_entered = threading.Event()
    release_first = threading.Event()
    original = BackupExecutor._run_claimed

    def blocked_run(executor, *args, **kwargs):
        first_entered.set()
        release_first.wait(3)
        return original(executor, *args, **kwargs)

    reports = [
        DiskHealth("source", str(src), "healthy", smart_status="Verified"),
        DiskHealth("target", str(dst), "healthy", smart_status="Verified"),
    ]
    first = svc.make_executor()
    second = svc.make_executor()
    result = []
    with patch.object(BackupExecutor, "_run_claimed", blocked_run), \
            patch("vaultguard.core.executor.check_backup_disks",
                  return_value=reports):
        thread = threading.Thread(
            target=lambda: result.append(
                first.run(tid, str(src), str(dst), resume=True)))
        thread.start()
        assert first_entered.wait(2)
        try:
            second.run(tid, str(src), str(dst), resume=True)
            raise AssertionError("duplicate execution should be rejected")
        except TaskAlreadyRunningError:
            pass
        release_first.set()
        thread.join(5)

    logs = svc.get_file_logs(tid)
    assert len(result) == 1 and result[0].copied == 1
    assert len(logs) == 1, len(logs)
    svc.close()
    shutil.rmtree(d)
    print("PASS test_duplicate_task_execution_is_rejected")


def test_failed_task_can_resume_only_undone_files():
    """失败任务应可续传，且已成功文件不会再次复制。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    setup_tree(src, {"a.txt": "a", "b.txt": "b"})
    svc = BackupService(data)
    diff = svc.compare(str(src), str(dst))
    tid = svc.create_task(str(src), str(dst), diff)
    reports = [
        DiskHealth("source", str(src), "healthy", smart_status="Verified"),
        DiskHealth("target", str(dst), "healthy", smart_status="Verified"),
    ]
    original = BackupExecutor._copy_with_retry

    def fail_b(executor, src_file, dst_file, progress_cb=None):
        if src_file.name == "b.txt":
            return False, False, "error_io:PermissionError"
        return original(executor, src_file, dst_file, progress_cb)

    with patch.object(BackupExecutor, "_copy_with_retry", fail_b), \
            patch("vaultguard.core.executor.check_backup_disks",
                  return_value=reports):
        first, _ = svc.execute(tid, str(src), str(dst))
    assert first.copied == 1 and first.failed == 1

    resumable = svc.find_resumable(str(src), str(dst))
    assert resumable is not None and resumable["id"] == tid
    with patch("vaultguard.core.executor.check_backup_disks",
               return_value=reports):
        second, _ = svc.execute(tid, str(src), str(dst), resume=True)

    logs = svc.get_file_logs(tid)
    a_logs = [row for row in logs if row["file_path"] == "a.txt"]
    assert second.copied == 2 and second.failed == 0
    assert len(a_logs) == 1, len(a_logs)
    assert (dst/"a.txt").read_text() == "a"
    assert (dst/"b.txt").read_text() == "b"
    svc.close()
    shutil.rmtree(d)
    print("PASS test_failed_task_can_resume_only_undone_files")


def test_delete_sync():
    """删除同步：源文件被删后，开启 delete_sync 应同步删除目标多余文件，
    并在 file_logs 中记录 delete 动作。"""
    d = tempfile.mkdtemp()
    src, dst, data = Path(d)/"s", Path(d)/"t", Path(d)/"data"
    setup_tree(src, {"keep.txt": "k", "stale/old.txt": "x", "stale/sub/deep.bin": b"y"})
    svc = BackupService(data)

    # 第一次完整备份，让目标拥有所有文件
    diff = svc.compare(str(src), str(dst))
    tid = svc.create_task(str(src), str(dst), diff)
    svc.execute(tid, str(src), str(dst))

    # 删除源文件，开启 delete_sync 后再次对比
    (src/"stale/old.txt").unlink()
    (src/"stale/sub/deep.bin").unlink()
    svc.settings.delete_sync = True
    svc.settings.use_recycle = False  # 测试中走物理删除避免触发 GUI 回收

    diff2 = svc.compare(str(src), str(dst))
    assert diff2.extra_count == 2, f"expected 2 extras, got {diff2.extra_count}"
    assert {it.rel_path for it in diff2.extra_items} == {
        "stale/old.txt", "stale/sub/deep.bin"
    }

    tid2 = svc.create_task(str(src), str(dst), diff2)
    prog, _ = svc.execute(tid2, str(src), str(dst))
    assert prog.deleted == 2 and prog.failed == 0, \
        f"deleted={prog.deleted} failed={prog.failed}"
    assert not (dst/"stale/old.txt").exists()
    assert not (dst/"stale/sub/deep.bin").exists()
    assert (dst/"keep.txt").exists()

    logs = svc.get_file_logs(tid2)
    actions = sorted(lg["action"] for lg in logs)
    assert actions == ["delete", "delete"], f"file_logs actions={actions}"

    task = svc.db.get_task(tid2)
    assert task["deleted_files"] == 2, task["deleted_files"]

    svc.close()
    shutil.rmtree(d)
    print("PASS test_delete_sync")


if __name__ == "__main__":
    test_atomicity_and_mtime()
    test_update_detection()
    test_failure_isolation()
    test_resume()
    test_exclude()
    test_scan_progress_is_continuous()
    test_macos_health_check_is_read_only()
    test_failing_target_health_blocks_backup()
    test_health_check_timeout_is_bounded()
    test_cancel_inside_large_file()
    test_isolated_hash_verification()
    test_rescue_stall_skips_and_continues()
    test_rescue_mode_never_deletes_target_files()
    test_duplicate_task_execution_is_rejected()
    test_failed_task_can_resume_only_undone_files()
    test_delete_sync()
    print("\n=== ALL TESTS PASSED ===")
