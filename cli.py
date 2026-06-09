#!/usr/bin/env python3
"""VaultGuard 命令行入口：先跑通核心对比与备份逻辑。

用法：
  python cli.py compare <源目录> <目标目录>
  python cli.py backup  <源目录> <目标目录> [--yes] [--resume]
  python cli.py history
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vaultguard.core.models import CopyProgress
from vaultguard.core.service import BackupService


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n}B"


def cmd_compare(svc: BackupService, args) -> int:
    diff = svc.compare(args.source, args.target)
    print(f"\n对比结果（源: {args.source} → 目标: {args.target}）")
    print(f"  新增 (new)    : {diff.new_count}")
    print(f"  更新 (updated): {diff.updated_count}")
    print(f"  跳过 (skip)   : {diff.skipped_count}")
    print(f"  预计传输      : {_fmt_size(diff.pending_bytes)}\n")
    if args.verbose:
        for it in diff.pending_items:
            print(f"  [{it.action.value:7}] {it.rel_path}  ({_fmt_size(it.size)})")
    return 0


def _progress_printer(prog: CopyProgress) -> None:
    pct = (prog.transferred_bytes / prog.total_bytes * 100) if prog.total_bytes else 100
    sys.stdout.write(
        f"\r  [{pct:5.1f}%] {prog.processed_files}/{prog.total_files} "
        f"复制{prog.copied} 失败{prog.failed} "
        f"{_fmt_size(int(prog.speed_bps))}/s  {prog.current_file[:40]:40}"
    )
    sys.stdout.flush()


def cmd_backup(svc: BackupService, args) -> int:
    source, target = args.source, args.target

    # 断点续传检测
    resumable = svc.find_resumable(source, target)
    resume = False
    task_id = None
    if resumable and not args.fresh:
        undone = svc.db.get_pending_items(resumable["id"], only_undone=True)
        if undone:
            print(f"检测到未完成任务 #{resumable['id']}（剩余 {len(undone)} 个文件）")
            if args.resume or args.yes:
                resume = True
                task_id = resumable["id"]
                print("→ 从断点继续")
            else:
                ans = input("从断点继续(c) / 重新开始(r)? [c/r]: ").strip().lower()
                if ans == "c":
                    resume = True
                    task_id = resumable["id"]

    if task_id is None:
        diff = svc.compare(source, target)
        print(f"\n待备份清单：新增 {diff.new_count} / 更新 {diff.updated_count} "
              f"/ 跳过 {diff.skipped_count}，预计传输 {_fmt_size(diff.pending_bytes)}")
        if not diff.pending_items:
            print("没有需要备份的文件，全部已是最新。")
            return 0
        # 先选后执行
        if not args.yes:
            ans = input("确认开始备份? [y/N]: ").strip().lower()
            if ans != "y":
                print("已取消。")
                return 0
        task_id = svc.create_task(source, target, diff)

    print(f"\n开始执行任务 #{task_id} ...")
    prog, _ = svc.execute(task_id, source, target, resume=resume,
                          progress_cb=_progress_printer)
    print(f"\n\n完成：复制 {prog.copied} / 失败 {prog.failed} / 共 {prog.total_files} 个。")
    if prog.failed:
        print("存在失败文件，可重新运行 backup 以重试。")
        return 1
    return 0


def cmd_history(svc: BackupService, args) -> int:
    tasks = svc.list_tasks()
    if not tasks:
        print("暂无历史任务。")
        return 0
    print(f"{'ID':>4}  {'状态':<10}  {'复制':>6}  {'失败':>6}  源 → 目标")
    for t in tasks:
        print(f"{t['id']:>4}  {t['status']:<10}  {t['copied_files']:>6}  "
              f"{t['failed_files']:>6}  {t['source_path']} → {t['target_path']}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="备份了嘛 增量备份 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_cmp = sub.add_parser("compare", help="对比源与目标，打印清单（不复制）")
    p_cmp.add_argument("source")
    p_cmp.add_argument("target")
    p_cmp.add_argument("-v", "--verbose", action="store_true", help="打印每个文件")

    p_bak = sub.add_parser("backup", help="对比并执行备份")
    p_bak.add_argument("source")
    p_bak.add_argument("target")
    p_bak.add_argument("-y", "--yes", action="store_true", help="跳过确认")
    p_bak.add_argument("--resume", action="store_true", help="自动从断点继续")
    p_bak.add_argument("--fresh", action="store_true", help="忽略断点，重新开始")

    sub.add_parser("history", help="查看历史任务")

    args = parser.parse_args(argv)
    svc = BackupService()
    try:
        if args.command == "compare":
            return cmd_compare(svc, args)
        elif args.command == "backup":
            return cmd_backup(svc, args)
        elif args.command == "history":
            return cmd_history(svc, args)
    finally:
        svc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
