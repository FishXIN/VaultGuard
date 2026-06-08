"""模块 1：文件扫描与对比引擎。

软件的心脏：递归遍历源目录，与目标目录对比，输出「新增/更新/跳过」清单。
此模块只对比、不复制。
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Callable, Iterator, Optional

from .models import Action, DiffItem, DiffResult, FileEntry


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


def compare(
    source: str | Path,
    target: str | Path,
    *,
    mtime_tolerance: float = 2.0,
    compare_size: bool = True,
    exclude_patterns: Optional[list[str]] = None,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> DiffResult:
    """对比源目录与目标目录，生成待备份清单。

    判定规则：
      - 新增（new）：目标端不存在 → 需复制
      - 更新（updated）：源端 mtime 更新（超过容差），或大小不同 → 需覆盖
      - 跳过（skip）：目标端已存在且不比源端旧

    mtime 对比留容差，规避 FAT32 等文件系统精度差异导致的误判。
    """
    source = Path(source)
    target = Path(target)
    exclude_patterns = exclude_patterns or []
    result = DiffResult()

    count = 0
    for entry in scan_directory(source, exclude_patterns):
        count += 1
        if progress_cb and count % 200 == 0:
            progress_cb(count)

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
        progress_cb(count)
    return result
