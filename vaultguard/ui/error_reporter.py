"""Error capture and one-click feedback helpers for the desktop UI."""
from __future__ import annotations

import json
import platform
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import quote

from vaultguard.core.config import app_data_dir


FEEDBACK_EMAIL = "lllpmqlll2018@gmail.com"


class ErrorReporter:
    """Persist UI/runtime exceptions and build a mailto feedback draft."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.report_dir = (data_dir or app_data_dir()) / "error_reports"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.latest_json = self.report_dir / "latest_error.json"
        self.latest_text = self.report_dir / "latest_error.txt"

    def record_exception(self, context: str, exc: BaseException) -> dict:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        report = {
            "time": now,
            "context": context,
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
            "python": sys.version.replace("\n", " "),
            "platform": platform.platform(),
            "report_dir": str(self.report_dir),
        }
        self._write(report)
        return report

    def load_latest(self) -> dict | None:
        try:
            if not self.latest_json.exists():
                return None
            with open(self.latest_json, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def build_mailto(self, report: dict) -> str:
        subject = f"VaultGuard 错误反馈：{report.get('type', 'UnknownError')}"
        body = self.format_text(report)
        # Keep the URL short enough for default mail clients.
        if len(body) > 6000:
            body = body[:6000] + "\n\n... 内容过长已截断，请查看本地 latest_error.txt ..."
        return (
            f"mailto:{FEEDBACK_EMAIL}"
            f"?subject={quote(subject)}&body={quote(body)}"
        )

    def format_text(self, report: dict) -> str:
        return (
            "VaultGuard 错误反馈\n"
            f"时间：{report.get('time', '')}\n"
            f"场景：{report.get('context', '')}\n"
            f"类型：{report.get('type', '')}\n"
            f"内容：{report.get('message', '')}\n"
            f"系统：{report.get('platform', '')}\n"
            f"Python：{report.get('python', '')}\n"
            f"本地报告目录：{report.get('report_dir', '')}\n\n"
            "Traceback:\n"
            f"{report.get('traceback', '')}"
        )

    def _write(self, report: dict) -> None:
        with open(self.latest_json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        with open(self.latest_text, "w", encoding="utf-8") as f:
            f.write(self.format_text(report))
