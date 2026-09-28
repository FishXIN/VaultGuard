"""Read-only disk health checks used before each backup.

The checks only query operating-system metadata. They never start SMART
self-tests, scan disk sectors, benchmark writes, repair filesystems, or mount
and unmount volumes.
"""
from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class DiskHealth:
    role: str
    path: str
    status: str
    device: str = ""
    name: str = ""
    smart_status: str = ""
    free_bytes: int = 0
    total_bytes: int = 0
    read_only: bool = False
    detail: str = ""


def _nearest_existing(path: str | Path) -> Path:
    current = Path(path).expanduser().resolve(strict=False)
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def _usage(path: Path) -> tuple[int, int]:
    try:
        usage = shutil.disk_usage(path)
        return usage.free, usage.total
    except OSError:
        return 0, 0


def _status_from_value(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"verified", "healthy", "ok", "online"}:
        return "healthy"
    if normalized in {"failing", "failed", "unhealthy", "critical", "error"}:
        return "failing"
    if normalized in {"warning", "degraded", "pred fail", "predictive failure"}:
        return "warning"
    return "unknown"


def _macos_health(role: str, original: str, existing: Path) -> DiskHealth:
    free_bytes, total_bytes = _usage(existing)
    try:
        df = subprocess.run(
            ["df", "-P", str(existing)],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        lines = [line for line in df.stdout.splitlines() if line.strip()]
        if df.returncode != 0 or len(lines) < 2:
            raise RuntimeError("df did not resolve a device")
        device = lines[-1].split()[0]
        info_proc = subprocess.run(
            ["diskutil", "info", "-plist", device],
            capture_output=True,
            timeout=5,
            check=False,
        )
        if info_proc.returncode != 0:
            raise RuntimeError("diskutil could not read device metadata")
        info = plistlib.loads(info_proc.stdout)
        if info.get("Error"):
            raise RuntimeError(str(info.get("ErrorMessage", "diskutil error")))

        smart = str(info.get("SMARTStatus", ""))
        status = _status_from_value(smart)
        writable = bool(info.get("WritableVolume", info.get("Writable", True)))
        return DiskHealth(
            role=role,
            path=original,
            status=status,
            device=str(info.get("DeviceNode", device)),
            name=str(info.get("VolumeName") or info.get("MediaName") or device),
            smart_status=smart or "Not Supported",
            free_bytes=free_bytes,
            total_bytes=total_bytes,
            read_only=not writable,
            detail=(
                "SMART metadata verified by diskutil"
                if status == "healthy"
                else "SMART status unavailable or requires attention"
            ),
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired, plistlib.InvalidFileException) as exc:
        return DiskHealth(
            role=role,
            path=original,
            status="unknown",
            free_bytes=free_bytes,
            total_bytes=total_bytes,
            detail=f"Unable to query disk metadata: {exc}",
        )


def _windows_health(role: str, original: str, existing: Path) -> DiskHealth:
    free_bytes, total_bytes = _usage(existing)
    drive = os.path.splitdrive(str(existing))[0].rstrip(":")
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not drive or not powershell:
        return DiskHealth(
            role=role,
            path=original,
            status="unknown",
            free_bytes=free_bytes,
            total_bytes=total_bytes,
            detail="Windows disk health interface is unavailable",
        )

    script = (
        f"$d=Get-Partition -DriveLetter '{drive}' -ErrorAction Stop | "
        "Get-Disk -ErrorAction Stop | Select-Object -First 1 "
        "Number,FriendlyName,HealthStatus,OperationalStatus,BusType,IsReadOnly;"
        "$d | ConvertTo-Json -Compress"
    )
    try:
        proc = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError("Get-Disk could not read device metadata")
        info = json.loads(proc.stdout)
        health = str(info.get("HealthStatus", ""))
        operational = info.get("OperationalStatus", "")
        if isinstance(operational, list):
            operational = ", ".join(str(item) for item in operational)
        status = _status_from_value(health)
        return DiskHealth(
            role=role,
            path=original,
            status=status,
            device=str(info.get("Number", "")),
            name=str(info.get("FriendlyName", "")),
            smart_status=health or "Unknown",
            free_bytes=free_bytes,
            total_bytes=total_bytes,
            read_only=bool(info.get("IsReadOnly", False)),
            detail=f"Operational status: {operational or 'Unknown'}",
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return DiskHealth(
            role=role,
            path=original,
            status="unknown",
            free_bytes=free_bytes,
            total_bytes=total_bytes,
            detail=f"Unable to query disk metadata: {exc}",
        )


def check_disk_health(path: str | Path, role: str) -> DiskHealth:
    """Return a best-effort, non-invasive health snapshot for one path."""
    original = str(path)
    existing = _nearest_existing(path)
    if sys.platform == "darwin":
        return _macos_health(role, original, existing)
    if sys.platform.startswith("win"):
        return _windows_health(role, original, existing)

    free_bytes, total_bytes = _usage(existing)
    return DiskHealth(
        role=role,
        path=original,
        status="unknown",
        free_bytes=free_bytes,
        total_bytes=total_bytes,
        detail="No read-only SMART integration is available on this platform",
    )


def check_backup_disks(source: str | Path, target: str | Path) -> list[DiskHealth]:
    """Check both disks in killable subprocesses with a bounded wait."""
    return [
        _check_disk_health_bounded(source, "source"),
        _check_disk_health_bounded(target, "target"),
    ]


def _check_disk_health_bounded(
    path: str | Path,
    role: str,
    timeout: float = 8.0,
) -> DiskHealth:
    env = os.environ.copy()
    env["VAULTGUARD_HEALTH_WORKER"] = "1"
    env.pop("VAULTGUARD_COPY_WORKER", None)
    env.pop("VAULTGUARD_DIR_PICKER", None)
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.append(str(Path(__file__).resolve().parents[2] / "main.py"))

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = None
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
            creationflags=creationflags,
        )
        output, _ = proc.communicate(
            json.dumps({"path": str(path), "role": role}) + "\n",
            timeout=timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError("health worker exited unexpectedly")
        return DiskHealth(**json.loads(output))
    except subprocess.TimeoutExpired:
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass
        return DiskHealth(
            role=role,
            path=str(path),
            status="warning" if role == "source" else "unknown",
            detail=f"Disk health check exceeded {timeout:g} seconds",
        )
    except (OSError, RuntimeError, TypeError, json.JSONDecodeError) as exc:
        return DiskHealth(
            role=role,
            path=str(path),
            status="unknown",
            detail=f"Unable to run bounded disk health check: {exc}",
        )


def run_health_worker() -> None:
    line = sys.stdin.readline()
    request = json.loads(line)
    report = check_disk_health(request["path"], request["role"])
    sys.stdout.write(json.dumps(asdict(report), ensure_ascii=True))
    sys.stdout.flush()


def format_health_summary(reports: Iterable[DiskHealth]) -> str:
    labels = {
        "healthy": "正常",
        "warning": "需注意",
        "failing": "故障",
        "unknown": "无法读取 SMART",
    }
    roles = {"source": "源盘", "target": "目标盘"}
    return "；".join(
        f"{roles.get(report.role, report.role)}："
        f"{labels.get(report.status, report.status)}"
        for report in reports
    )
