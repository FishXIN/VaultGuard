"""通用 UI 辅助函数。"""
from __future__ import annotations


def fmt_size(n: int | float) -> str:
    """人类可读的字节大小。"""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_eta(seconds: float) -> str:
    """剩余时间格式化。"""
    if seconds <= 0 or seconds != seconds:  # 0 或 NaN
        return "--"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds // 60} 分 {seconds % 60} 秒"
    return f"{seconds // 3600} 时 {(seconds % 3600) // 60} 分"


def fmt_time(ts: int | None) -> str:
    """时间戳格式化。"""
    if not ts:
        return "--"
    import time
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def fmt_relative_time(ts: int | None, now: int | None = None) -> str:
    """将时间戳格式化为面向用户的相对时间。"""
    if not ts:
        return "--"
    import time
    now = int(time.time()) if now is None else int(now)
    seconds = max(0, now - int(ts))
    if seconds < 5:
        return "刚刚"
    if seconds < 60:
        return f"{seconds}秒之前"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}分钟之前"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}小时之前"
    days = hours // 24
    if days < 7:
        return f"{days}天之前"
    weeks = days // 7
    if weeks < 4:
        return f"{weeks}周之前"
    months = days // 30
    if months < 12:
        return f"{max(months, 1)}月之前"
    years = days // 365
    return f"{max(years, 1)}年之前"
