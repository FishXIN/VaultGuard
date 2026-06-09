"""模块 1：文件扫描与对比引擎。

软件的心脏：递归遍历源目录，与目标目录对比，输出「新增/更新/跳过」清单。
此模块只对比、不复制。
"""
from __future__ import annotations

import fnmatch
import os
import time
from pathlib import Path
from typing import Callable, Iterator, Optional

from .models import Action, CompareProgress, DiffItem, DiffResult, FileEntry


def _matches_exclude(name: str, rel_path: str, patterns: list[str]) -> bool:
    """判断文件名或相对路径是否命中排除规则。"""
    for pat in patterns:
        if fnmatch.fnmatch(name, pat):
            return True
        # 按目录名忽略（如 node_modules）
        parts = Path(rel_path).parts
        if pat in parts:
            return True
    return False


def scan_directory(
    root: str | Path,
    exclude_patterns: Optional[list[str]] = None,
    follow_symlinks: bool = False,
) -> Iterator[FileEntry]:
    """递归遍历目录，产出每个文件的相对路径、大小、mtime。

    - 不独占锁定源文件（只读 stat）。
    - 安全处理符号链接：默认不跟随，避免循环引用。
    """
    root = Path(root)
    exclude_patterns = exclude_patterns or []
    visited_dirs: set[tuple[int, int]] = set()  # (st_dev, st_ino) 防循环

    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        # 过滤被排除的目录，避免深入遍历
        pruned = []
        for d in dirnames:
            full = os.path.join(dirpath, d)
            rel = os.path.relpath(full, root)
            if _matches_exclude(d, rel, exclude_patterns):
                continue
            # 防符号链接循环引用
            if follow_symlinks:
                try:
                    st = os.stat(full)
                    key = (st.st_dev, st.st_ino)
                    if key in visited_dirs:
                        continue
                    visited_dirs.add(key)
                except OSError:
                    continue
            pruned.append(d)
        dirnames[:] = pruned

        for fname in filenames:
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, root)
            if _matches_exclude(fname, rel, exclude_patterns):
                continue
            # 跳过符号链接文件（安全：不跟随）
            if os.path.islink(full) and not follow_symlinks:
                continue
            try:
                st = os.stat(full)
            except OSError:
                # 无法访问的文件跳过，不中断扫描
                continue
            if not os.path.isfile(full):
                continue
            yield FileEntry(rel_path=rel, size=st.st_size, mtime=st.st_mtime)


def _count_files_with_progress(
    root: Path,
    exclude_patterns: list[str],
    emit: Callable[[int, float, str], None],
) -> int:
    """统计文件数量，并按真实扫描工作量连续输出确定态进度。

    文件总量在统计完成前天然未知，因此这里用已扫描文件、目录和目录项构成
    单调递增的进度估算；它不是无意义动画，进度只随实际扫描推进而推进。
    """
    stack = [root]
    processed_dirs = 0
    scanned_entries = 0
    total_files = 0
    last_emit_at = 0.0
    last_ratio = 0.0

    def estimate_ratio() -> float:
        work_units = total_files + processed_dirs * 12 + scanned_entries * 0.15
        if work_units <= 0:
            return 0.0
        return min(0.98, work_units / (work_units + 500))

    def send(current_file: str = "", force: bool = False) -> None:
        nonlocal last_emit_at, last_ratio
        now = time.monotonic()
        if not force and now - last_emit_at < 0.08:
            return
        last_emit_at = now
        last_ratio = max(last_ratio, estimate_ratio())
        emit(total_files, last_ratio, current_file)

    emit(0, 0.0, "")
    while stack:
        dirpath = stack.pop()
        processed_dirs += 1
        send(str(dirpath.relative_to(root)) if dirpath != root else "", force=True)
        try:
            entries = os.scandir(dirpath)
        except OSError:
            send(force=True)
            continue

        with entries:
            for entry in entries:
                scanned_entries += 1
                rel = os.path.relpath(entry.path, root)
                if _matches_exclude(entry.name, rel, exclude_patterns):
                    send(rel)
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                        send(rel, force=True)
                    elif entry.is_file(follow_symlinks=False):
                        total_files += 1
                        send(rel, force=True)
                    else:
                        send(rel, force=True)
                except OSError:
                    send(rel, force=True)
                    continue

        send(force=True)

    emit(total_files, 1.0, "")
    return total_files


def compare(
    source: str | Path,
    target: str | Path,
    *,
    mtime_tolerance: float = 2.0,
    compare_size: bool = True,
    exclude_patterns: Optional[list[str]] = None,
    find_extras: bool = False,
    progress_cb: Optional[Callable[[CompareProgress], None]] = None,
) -> DiffResult:
    """对比源目录与目标目录，生成待备份清单。

    判定规则：
      - 新增（new）：目标端不存在 → 需复制
      - 更新（updated）：源端 mtime 更新（超过容差），或大小不同 → 需覆盖
      - 跳过（skip）：目标端已存在且不比源端旧
      - 多余（extra）：``find_extras=True`` 时，目标端存在但源端已不存在
        的文件，会进入 ``extra_items``，供调用方决定是否同步删除。

    mtime 对比留容差，规避 FAT32 等文件系统精度差异导致的误判。
    """
    source = Path(source)
    target = Path(target)
    exclude_patterns = exclude_patterns or []
    result = DiffResult()
    started_at = time.monotonic()

    def emit(
        phase: str,
        processed: int,
        total: int,
        current_file: str = "",
        finished: bool = False,
        progress_ratio: float = 0.0,
    ) -> None:
        if not progress_cb:
            return
        elapsed = time.monotonic() - started_at
        eta = 0.0
        if phase == "comparing" and processed > 0 and total > 0 and not finished:
            eta = (elapsed / processed) * max(total - processed, 0)
        progress_cb(CompareProgress(
            phase=phase,
            current_file=current_file,
            processed_files=processed,
            total_files=total,
            progress_ratio=progress_ratio,
            elapsed_seconds=elapsed,
            eta_seconds=eta,
            finished=finished,
        ))

    total_files = 0
    if progress_cb:
        def scan_emit(count: int, ratio: float, current_file: str) -> None:
            emit("scanning", count, 0, current_file, progress_ratio=ratio)

        total_files = _count_files_with_progress(source, exclude_patterns, scan_emit)
        emit("comparing", 0, total_files, progress_ratio=0.0)
        started_at = time.monotonic()

    count = 0
    for entry in scan_directory(source, exclude_patterns):
        count += 1
        if progress_cb:
            ratio = (count / total_files) if total_files else 0.0
            emit("comparing", count, total_files, entry.rel_path,
                 progress_ratio=ratio)

        dst = target / entry.rel_path
        if not dst.exists():
            result.new_items.append(
                DiffItem(entry.rel_path, Action.NEW, entry.size,
                         entry.mtime, None, "new")
            )
            continue

        try:
            dst_st = dst.stat()
        except OSError:
            # 目标无法 stat，保守起见当作需更新
            result.updated_items.append(
                DiffItem(entry.rel_path, Action.UPDATED, entry.size,
                         entry.mtime, None, "updated")
            )
            continue

        size_diff = compare_size and (dst_st.st_size != entry.size)
        # 源端比目标端更新（超过容差）才算 updated
        mtime_newer = entry.mtime - dst_st.st_mtime > mtime_tolerance

        if size_diff or mtime_newer:
            reason = "updated"
            result.updated_items.append(
                DiffItem(entry.rel_path, Action.UPDATED, entry.size,
                         entry.mtime, dst_st.st_mtime, reason)
            )
        else:
            result.skipped_items.append(
                DiffItem(entry.rel_path, Action.SKIP, entry.size,
                         entry.mtime, dst_st.st_mtime, "unchanged")
            )

    if progress_cb:
        emit("comparing", count, total_files or count, finished=True,
             progress_ratio=1.0)

    if find_extras and target.exists():
        # 反向扫描目标目录，找出源端已删除（或被排除规则隔离）的文件。
        source_rels = {
            it.rel_path for it in result.new_items
        } | {it.rel_path for it in result.updated_items} | {
            it.rel_path for it in result.skipped_items
        }
        for entry in scan_directory(target, exclude_patterns):
            if entry.rel_path in source_rels:
                continue
            src_file = source / entry.rel_path
            if src_file.exists():
                # 源文件存在但被排除/无法 stat：保守起见不视作多余
                continue
            result.extra_items.append(
                DiffItem(entry.rel_path, Action.EXTRA, entry.size,
                         entry.mtime, entry.mtime, "extra")
            )
    return result
