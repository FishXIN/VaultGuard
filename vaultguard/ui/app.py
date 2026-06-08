"""VaultGuard 桌面图形界面（模块 5 + 6）。

视觉与交互严格遵循 VaultGuard-Design-System.md（v2.0 · 火山引擎 / Arco 极简风）：
- 色彩：黑白灰为主（≈90%）+ 单一克制蓝 #165DFF（≈8%）+ 低饱和状态色（<2%）
- 圆角：按钮/输入框 4 / 卡片/弹窗 6 / 大容器 8，无大圆角
- 阴影：平铺内容用边框分隔，阴影仅给浮层（弹窗）
- 字体：14px 正文，标题用 medium(500)；路径/容量/速率用等宽字体
- 动效：仅颜色过渡 / 淡入，≤250ms，无发光、无流光、无渐变、无回弹
- 进度条：纯色按真实 width 推进，不做装饰动画
- 状态标签：success / warning / danger / running
"""
from __future__ import annotations

import asyncio
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable, Optional

from vaultguard.core.models import CompareProgress, CopyProgress, DiffResult
from vaultguard.core.service import BackupService
from . import tokens as T
from .error_reporter import ErrorReporter
from .helpers import fmt_eta, fmt_size, fmt_time
from .runtime import VIEW_PATH_ENV, ft


# ============ 侧边导航图标（内联 assets/Icon 下的 SVG，随模块自包含） ============
# 设计稿描边色固定为 #0B0B0F，运行时通过 ft.Image 的 SRC_IN 着色为选中/未选中色。
_NAV_SVG_TASK = (
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<path d="M2 3.99998L2.9 4.89998L4.5 3.09998" stroke="#0B0B0F" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M2 7.99998L2.9 8.89998L4.5 7.09998" stroke="#0B0B0F" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M2 12L2.9 12.9L4.5 11.1" stroke="#0B0B0F" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M6.5 4H14" stroke="#0B0B0F" stroke-linecap="round"/>'
    '<path d="M6.5 8H14" stroke="#0B0B0F" stroke-linecap="round"/>'
    '<path d="M6.5 12H14" stroke="#0B0B0F" stroke-linecap="round"/>'
    '</svg>'
)
_NAV_SVG_HISTORY = (
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<path d="M11.5 4.20001H12.4C12.96 4.20001 13.2 4.44001 13.2 5.00001V12.6C13.2 '
    '13.16 12.96 13.4 12.4 13.4H6.59999C6.03999 13.4 5.79999 13.16 5.79999 '
    '12.6V12.2" stroke="#0B0B0F" stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M3.59999 3H8.69999L10.2 4.5V10.6C10.2 11.16 9.95999 11.4 9.39999 '
    '11.4H3.59999C3.03999 11.4 2.79999 11.16 2.79999 10.6V3.8C2.79999 3.24 3.03999 '
    '3 3.59999 3Z" stroke="#0B0B0F" stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M4.70001 6.20001H8.30001M4.70001 8.40001H8.30001" stroke="#0B0B0F" '
    'stroke-linecap="round"/>'
    '</svg>'
)
_NAV_SVG_SETTING = (
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<path d="M6.68316 3.5C6.76316 3.2 7.03316 3 7.34316 3H8.62316C8.93316 3 9.20316 '
    '3.2 9.28316 3.5L9.53316 4.48C9.88316 4.6 10.2132 4.79 10.5032 5.02L11.4732 '
    '4.74C11.7632 4.66 12.0832 4.78 12.2332 5.05L12.8732 6.16C13.0332 6.43 12.9832 '
    '6.76 12.7532 6.97L12.0232 7.66C12.0532 7.84 12.0632 8.02 12.0632 8.2C12.0632 '
    '8.38 12.0532 8.56 12.0232 8.74L12.7532 9.43C12.9832 9.64 13.0332 9.97 12.8732 '
    '10.24L12.2332 11.35C12.0832 11.62 11.7632 11.74 11.4732 11.66L10.5032 '
    '11.38C10.2132 11.61 9.88316 11.8 9.53316 11.92L9.28316 12.9C9.20316 13.2 '
    '8.93316 13.4 8.62316 13.4H7.34316C7.03316 13.4 6.76316 13.2 6.68316 '
    '12.9L6.43316 11.92C6.08316 11.8 5.75316 11.61 5.46316 11.38L4.49316 '
    '11.66C4.20316 11.74 3.88316 11.62 3.73316 11.35L3.09316 10.24C2.93316 9.97 '
    '2.98316 9.64 3.21316 9.43L3.94316 8.74C3.91316 8.56 3.90316 8.38 3.90316 '
    '8.2C3.90316 8.02 3.91316 7.84 3.94316 7.66L3.21316 6.97C2.98316 6.76 2.93316 '
    '6.43 3.09316 6.16L3.73316 5.05C3.88316 4.78 4.20316 4.66 4.49316 4.74L5.46316 '
    '5.02C5.75316 4.79 6.08316 4.6 6.43316 4.48L6.68316 3.5Z" stroke="#0B0B0F" '
    'stroke-linejoin="round"/>'
    '<path d="M7.98314 9.9C8.92203 9.9 9.68314 9.13888 9.68314 8.2C9.68314 7.26112 '
    '8.92203 6.5 7.98314 6.5C7.04426 6.5 6.28314 7.26112 6.28314 8.2C6.28314 9.13888 '
    '7.04426 9.9 7.98314 9.9Z" stroke="#0B0B0F" stroke-linejoin="round"/>'
    '</svg>'
)


def _nav_svg_icon(svg: str, color: str, size: int = 18) -> "ft.Image":
    """把内联 SVG 渲染为指定颜色的图标（SRC_IN 将描边整体着色）。"""
    return ft.Image(
        src=svg, width=size, height=size,
        color=color, color_blend_mode=ft.BlendMode.SRC_IN,
        fit=ft.BoxFit.CONTAIN,
    )


# ============ 通用 UI 工厂 ============

def _badge(label: str, kind: str = "running") -> ft.Container:
    """状态标签（规范 §5.3 .vg-tag）。kind ∈ success/warning/danger/running。"""
    palette = {
        "success": (T.SUCCESS, T.SUCCESS_BG),
        "warning": (T.WARNING, T.WARNING_BG),
        "danger": (T.DANGER, T.DANGER_BG),
        "running": (T.RUNNING, T.RUNNING_BG),
    }
    fg, bg = palette.get(kind, palette["running"])
    return ft.Container(
        content=ft.Row([
            ft.Container(width=6, height=6, bgcolor=fg, border_radius=3),
            ft.Text(label, size=T.TEXT_12, weight=T.FW_MEDIUM, color=fg),
        ], spacing=T.SP_1, tight=True),
        bgcolor=bg,
        border_radius=T.RADIUS_SM,
        padding=ft.Padding.symmetric(vertical=0, horizontal=T.SP_2),
        height=22,
        alignment=ft.Alignment.CENTER,
    )


def _primary_button(text: str, icon=None, on_click=None,
                    disabled: bool = False) -> ft.Container:
    """主按钮：实心蓝（规范 §5.1 .vg-btn--primary）。

    无上浮、无 glow、无 scale；hover 仅变背景色。
    """
    children = []
    if icon is not None:
        children.append(ft.Icon(icon, color=T.BG, size=16))
    children.append(ft.Text(text, color=T.BG,
                            size=T.TEXT_14, weight=T.FW_MEDIUM))
    inner = ft.Row(children, spacing=T.SP_2, tight=True,
                   alignment=ft.MainAxisAlignment.CENTER,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER)
    btn = ft.Container(
        content=inner,
        bgcolor=T.TEXT_DISABLED if disabled else T.PRIMARY,
        border_radius=T.RADIUS,
        padding=ft.Padding.symmetric(vertical=0, horizontal=T.SP_4),
        height=32,
        alignment=ft.Alignment.CENTER,
        animate=ft.Animation(T.DUR_FAST, T.EASE),
        on_click=(None if disabled else on_click),
        ink=False,
    )

    def _hover(e: ft.HoverEvent) -> None:
        if disabled:
            return
        try:
            btn.bgcolor = T.PRIMARY_HOVER if e.data == "true" else T.PRIMARY
            btn.update()
        except Exception:
            pass

    if not disabled:
        btn.on_hover = _hover
    return btn


def _default_button(text: str, icon=None, on_click=None,
                    danger: bool = False, disabled: bool = False,
                    tooltip: Optional[str] = None) -> ft.Container:
    """次按钮：描边（规范 §5.1 .vg-btn--default）。

    hover 仅变边框/文字色为主色；danger 变体用危险色描边。
    """
    base_color = T.TEXT_DISABLED if disabled else (
        T.DANGER if danger else T.TEXT_PRIMARY)
    base_border = T.BORDER_LIGHT if disabled else (
        T.DANGER if danger else T.BORDER)
    hover_color = T.DANGER if danger else T.PRIMARY

    label = ft.Text(text, color=base_color, size=T.TEXT_14, weight=T.FW_MEDIUM)
    children = []
    if icon is not None:
        children.append(ft.Icon(icon, color=base_color, size=16))
    children.append(label)
    inner = ft.Row(children, spacing=T.SP_2, tight=True,
                   alignment=ft.MainAxisAlignment.CENTER,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER)
    icon_ctrl = children[0] if icon is not None else None

    btn = ft.Container(
        content=inner,
        bgcolor=T.BG,
        border=ft.Border.all(1, base_border),
        border_radius=T.RADIUS,
        padding=ft.Padding.symmetric(vertical=0, horizontal=T.SP_4),
        height=32,
        alignment=ft.Alignment.CENTER,
        animate=ft.Animation(T.DUR_FAST, T.EASE),
        on_click=None if disabled else on_click,
        tooltip=tooltip,
        ink=False,
    )

    def _hover(e: ft.HoverEvent) -> None:
        if disabled:
            return
        try:
            on = e.data == "true"
            col = hover_color if on else base_color
            bdr = hover_color if on else base_border
            btn.border = ft.Border.all(1, bdr)
            label.color = col
            if icon_ctrl is not None:
                icon_ctrl.color = col
            btn.update()
        except Exception:
            pass

    if not disabled:
        btn.on_hover = _hover
    return btn


def _card(*controls, padding: int = T.SP_5,
          expand: Optional[bool] = None) -> ft.Container:
    """卡片 / 面板（规范 §5.2 .vg-card）：边框分隔，无阴影。"""
    column = ft.Column(list(controls), spacing=T.SP_3, tight=True)
    return ft.Container(
        content=column,
        bgcolor=T.BG,
        border_radius=T.RADIUS_MD,
        padding=padding,
        border=ft.Border.all(1, T.BORDER),
        expand=expand,
    )


def _section_title(text: str) -> ft.Text:
    return ft.Text(text, size=T.TEXT_16, weight=T.FW_MEDIUM,
                   color=T.TEXT_TITLE, font_family=T.FONT_SANS)


def _muted_text(text: str, size: int = T.TEXT_13) -> ft.Text:
    return ft.Text(text, size=size, color=T.TEXT_TERTIARY,
                   font_family=T.FONT_SANS)


def _mono_text(text: str, size: int = T.TEXT_13,
               color: str = T.TEXT_PRIMARY) -> ft.Text:
    """数据/容量/速率展示（规范 §2 推荐 mono 字体）。"""
    return ft.Text(text, size=size, color=color, font_family=T.FONT_MONO)


def _progress_track(height: int = 12, width: int = 640) -> ft.Container:
    """固定像素进度条，避免原生 ProgressBar 在桌面端渲染不可见。"""
    track = ft.Container(
        width=width,
        height=height,
        bgcolor=T.PRIMARY_BG,
        border=ft.Border.all(1, T.PRIMARY_BG),
        border_radius=T.RADIUS_SM,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        alignment=ft.Alignment.CENTER_LEFT,
    )
    track.data = {"width": width, "height": height}
    return track


def _set_progress_value(track: ft.Container, pct: float) -> None:
    pct = max(0.0, min(1.0, pct))
    data = track.data or {}
    width = int(data.get("width", 640))
    height = int(data.get("height", 12))
    fill_width = 0 if pct <= 0 else max(8, int(width * pct))
    track.content = ft.Container(
        width=min(fill_width, width),
        height=height,
        bgcolor=T.PRIMARY,
        border_radius=T.RADIUS_SM,
        animate=ft.Animation(T.DUR_FAST, T.EASE),
    )


# ============ 应用主体 ============

class VaultGuardApp:
    """应用主体，管理页面路由与状态。"""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.svc = BackupService()
        self.error_reporter = ErrorReporter(self.svc.data_dir)
        self.executor = None
        self.current_diff: Optional[DiffResult] = None
        self.current_task_id: Optional[int] = None
        self.source_path = self.svc.settings.last_source
        self.target_path = self.svc.settings.last_target
        self._running = False
        self._nav_index = 0
        self._nav_items: list[ft.Container] = []
        self._task_stage = "home"
        self._task_content = None
        self._compare_started_at = 0.0
        # 数据采集与界面刷新解耦：扫描线程只写快照，由独立节流线程统一重绘
        self._latest_compare_prog: Optional[CompareProgress] = None
        self._compare_refreshing = False
        self._latest_copy_prog: Optional[CopyProgress] = None
        self._copy_refreshing = False
        self._last_log_file = ""

        self._setup_page()
        self._build_layout()
        self._reset_task_home()

    # ---------- 页面基础 ----------
    def _setup_page(self) -> None:
        p = self.page
        p.title = "VaultGuard · 增量备份"
        p.bgcolor = T.BG
        p.theme_mode = ft.ThemeMode.LIGHT
        p.theme = ft.Theme(
            color_scheme_seed=T.PRIMARY,
            font_family="-apple-system",
            visual_density=ft.VisualDensity.COMFORTABLE,
        )
        p.window.width = 1120
        p.window.height = 760
        p.window.min_width = 960
        p.window.min_height = 640
        p.padding = 0

    def _build_layout(self) -> None:
        # 左侧固定侧边导航（宽 200px，选中项左侧 2px 蓝条 + 浅蓝底 + 蓝色文字）
        nav_defs = [
            (_NAV_SVG_TASK, "任务"),
            (_NAV_SVG_HISTORY, "历史"),
            (_NAV_SVG_SETTING, "设置"),
        ]
        self._nav_items = []
        for idx, (icon, label) in enumerate(nav_defs):
            self._nav_items.append(self._make_nav_item(idx, icon, label))

        sidebar = ft.Container(
            content=ft.Column(
                [ft.Container(height=T.SP_2),
                 *self._nav_items],
                spacing=T.SP_1,
            ),
            width=T.SIDEBAR_W,
            bgcolor=T.BG,
            border=ft.Border(right=ft.BorderSide(1, T.BORDER)),
        )

        self.content = ft.Container(
            expand=True,
            padding=T.SP_6,
            bgcolor=T.BG,
        )

        self.page.add(
            ft.Row(
                [sidebar, self.content],
                expand=True,
                spacing=0,
            )
        )

    def _make_nav_item(self, idx: int, icon, label: str) -> ft.Container:
        active = idx == self._nav_index
        fg = T.PRIMARY if active else T.TEXT_PRIMARY
        item = ft.Container(
            content=ft.Row([
                _nav_svg_icon(icon, fg, 18),
                ft.Text(label, size=T.TEXT_14, weight=T.FW_MEDIUM, color=fg),
            ], spacing=T.SP_3, tight=True),
            height=40,
            padding=ft.Padding.only(left=T.SP_5 - 2, right=T.SP_4),
            margin=ft.Padding.symmetric(vertical=0, horizontal=T.SP_2),
            bgcolor=T.PRIMARY_BG if active else None,
            border=ft.Border(left=ft.BorderSide(
                2, T.PRIMARY if active else "#00000000")),
            border_radius=T.RADIUS,
            alignment=ft.Alignment.CENTER_LEFT,
            animate=ft.Animation(T.DUR_FAST, T.EASE),
            on_click=self._safe(label, lambda e, i=idx: self._on_nav_click(i)),
        )
        item.data = (idx, icon, label)

        def _hover(e: ft.HoverEvent, c=item) -> None:
            try:
                i = c.data[0]
                if i == self._nav_index:
                    return
                c.bgcolor = T.FILL if e.data == "true" else None
                c.update()
            except Exception:
                pass

        item.on_hover = _hover
        return item

    def _refresh_nav(self) -> None:
        for c in self._nav_items:
            idx, icon, label = c.data
            active = idx == self._nav_index
            fg = T.PRIMARY if active else T.TEXT_PRIMARY
            row = c.content
            row.controls[0].color = fg
            row.controls[1].color = fg
            c.bgcolor = T.PRIMARY_BG if active else None
            c.border = ft.Border(left=ft.BorderSide(
                2, T.PRIMARY if active else "#00000000"))
        self.page.update()

    def _on_nav_click(self, idx: int) -> None:
        self._nav_index = idx
        self._refresh_nav()
        if idx == 0:
            self._show_task()
        elif idx == 1:
            self._show_history()
        elif idx == 2:
            self._show_settings()

    def _set_content(self, control) -> None:
        self.content.content = control
        self.page.update()

    def _set_task_content(self, control) -> None:
        self._task_content = control
        if self._nav_index == 0:
            self._set_content(control)

    def _show_task(self) -> None:
        if self._task_content is None:
            self._show_home()
            return
        self._set_content(self._task_content)

    def _reset_task_home(self) -> None:
        self.current_diff = None
        self._task_stage = "home"
        self._show_home()

    def _run_ui(self, fn: Callable[[], None]) -> None:
        async def runner():
            try:
                fn()
            except Exception as ex:  # noqa: BLE001
                report = self._record_error("UI 执行失败", ex)
                try:
                    self._show_error_dialog(report)
                except Exception as inner:  # noqa: BLE001
                    self._record_error("错误弹窗展示失败", inner)

        try:
            if hasattr(self.page, "run_task"):
                self.page.run_task(runner)
            else:
                fn()
        except Exception as ex:  # noqa: BLE001
            self._record_error("UI 调度失败", ex)

    def _start_refresher(self, refresher: Callable, context: str) -> None:
        async def guarded_refresher():
            try:
                await refresher()
            except Exception as ex:  # noqa: BLE001
                self._handle_error(context, ex)

        try:
            if hasattr(self.page, "run_task"):
                self.page.run_task(guarded_refresher)
            else:
                raise RuntimeError("当前 VaultGuard 桌面运行时缺少 page.run_task")
        except Exception as ex:  # noqa: BLE001
            self._handle_error(context, ex)

    def _safe(self, context: str, fn: Callable) -> Callable:
        def wrapper(e=None):
            try:
                return fn(e)
            except Exception as ex:  # noqa: BLE001
                self._handle_error(context, ex)
                return None

        return wrapper

    def _record_error(self, context: str, exc: BaseException) -> dict:
        try:
            return self.error_reporter.record_exception(context, exc)
        except Exception:  # noqa: BLE001
            return {
                "context": context,
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": "",
            }

    def _handle_error(self, context: str, exc: BaseException) -> None:
        report = self._record_error(context, exc)
        self._run_ui(lambda: self._show_error_dialog(report))

    def _show_error_dialog(self, report: dict) -> None:
        title = report.get("type", "UnknownError")
        message = report.get("message", "")
        content = ft.Container(
            width=620,
            content=ft.Column([
                ft.Text("操作没有继续执行，错误内容已记录到本地。",
                        size=T.TEXT_14, color=T.TEXT_PRIMARY),
                ft.Text(f"场景：{report.get('context', '')}",
                        size=T.TEXT_13, color=T.TEXT_PRIMARY),
                ft.Text(f"类型：{title}",
                        size=T.TEXT_13, color=T.DANGER,
                        font_family=T.FONT_MONO),
                ft.Text(f"内容：{message or '(无详细信息)'}",
                        size=T.TEXT_13, color=T.TEXT_PRIMARY,
                        selectable=True),
                _muted_text(f"报告目录：{self.error_reporter.report_dir}",
                            size=T.TEXT_12),
            ], spacing=T.SP_2, tight=True),
        )
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("检测到错误",
                          weight=T.FW_MEDIUM, size=T.TEXT_16, color=T.TEXT_TITLE),
            content=content,
            shape=ft.RoundedRectangleBorder(radius=T.RADIUS_MD),
            actions=[
                _default_button("关闭",
                                on_click=self._safe(
                                    "关闭错误弹窗",
                                    lambda e: self._close_overlay(dlg))),
                _primary_button("发送反馈",
                                icon=ft.Icons.EMAIL_OUTLINED,
                                on_click=self._safe(
                                    "发送错误反馈",
                                    lambda e: self._send_error_report(report))),
            ],
        )
        self._open_overlay(dlg)

    def _send_error_report(self, report: Optional[dict] = None) -> None:
        report = report or self.error_reporter.load_latest()
        if not report:
            self._snack("暂无可发送的错误报告", error=True)
            return
        mailto = self.error_reporter.build_mailto(report)
        try:
            if hasattr(self.page, "launch_url"):
                self.page.launch_url(mailto)
            else:
                webbrowser.open(mailto)
        except Exception:
            webbrowser.open(mailto)
        self._snack("已打开邮件草稿，请确认后发送")

    def _open_overlay(self, control) -> None:
        try:
            if hasattr(self.page, "open"):
                self.page.open(control)
                return
        except Exception:  # noqa: BLE001
            pass

        if isinstance(control, ft.SnackBar):
            self.page.snack_bar = control
        elif isinstance(control, ft.AlertDialog):
            self.page.dialog = control
        else:
            self.page.overlay.append(control)
        control.open = True
        self.page.update()

    def _close_overlay(self, control) -> None:
        try:
            if hasattr(self.page, "close"):
                self.page.close(control)
                return
        except Exception:  # noqa: BLE001
            pass

        control.open = False
        self.page.update()

    def _snack(self, msg: str, error: bool = False) -> None:
        self._open_overlay(
            ft.SnackBar(
                ft.Text(msg, color=T.BG, weight=T.FW_MEDIUM),
                bgcolor=T.DANGER if error else T.SUCCESS,
                shape=ft.RoundedRectangleBorder(radius=T.RADIUS),
            )
        )

    def _page_header(self, title: str, subtitle: Optional[str] = None) -> ft.Column:
        items = [ft.Text(title, size=T.TEXT_28, weight=T.FW_MEDIUM,
                         color=T.TEXT_TITLE, font_family=T.FONT_SANS)]
        return ft.Column(items, spacing=T.SP_1, tight=True)

    # ========== 主页 ==========
    def _show_home(self) -> None:
        self._task_stage = "home"
        self.src_field = self._path_field(
            "源目录", self.source_path,
            "路径",
            lambda e: setattr(self, "source_path", e.control.value))
        self.dst_field = self._path_field(
            "目标目录", self.target_path,
            "路径",
            lambda e: setattr(self, "target_path", e.control.value))

        self._set_task_content(ft.Column([
            self._page_header("本地硬盘增量备份"),
            ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
            _card(
                _section_title("选择目录"),
                ft.Row([self.src_field, self._picker_btn(True)],
                       vertical_alignment=ft.CrossAxisAlignment.END,
                       spacing=T.SP_2),
                ft.Row([self.dst_field, self._picker_btn(False)],
                       vertical_alignment=ft.CrossAxisAlignment.END,
                       spacing=T.SP_2),
                ft.Container(height=T.SP_2),
                ft.Row([
                    _primary_button("开始对比",
                                    icon=ft.Icons.COMPARE_ARROWS_ROUNDED,
                                    on_click=self._safe(
                                        "开始对比", lambda e: self._do_compare())),
                ], alignment=ft.MainAxisAlignment.END),
            ),
        ], spacing=T.SP_5, scroll=ft.ScrollMode.AUTO))

    def _path_field(self, label, value, hint, on_change) -> ft.TextField:
        return ft.TextField(
            label=label,
            value=value,
            hint_text=hint,
            on_change=on_change,
            expand=True,
            border_radius=T.RADIUS,
            border_color=T.BORDER,
            focused_border_color=T.PRIMARY,
            cursor_color=T.PRIMARY,
            text_size=T.TEXT_14,
            content_padding=ft.Padding.symmetric(vertical=8, horizontal=12),
        )

    def _picker_btn(self, is_source: bool) -> ft.Container:
        prompt = "选择源目录" if is_source else "选择目标目录"
        b = ft.Container(
            content=ft.Icon(ft.Icons.FOLDER_OPEN_OUTLINED,
                            color=T.TEXT_PRIMARY, size=18),
            width=32, height=32,
            bgcolor=T.BG,
            border=ft.Border.all(1, T.BORDER),
            border_radius=T.RADIUS,
            alignment=ft.Alignment.CENTER,
            tooltip="选择源目录" if is_source else "选择目标目录",
            on_click=self._safe(prompt,
                                lambda e, s=is_source: self._pick_dir(s)),
            animate=ft.Animation(T.DUR_FAST, T.EASE),
        )

        def _hover(e: ft.HoverEvent, ctrl=b) -> None:
            try:
                on = e.data == "true"
                ctrl.border = ft.Border.all(1, T.PRIMARY if on else T.BORDER)
                ctrl.content.color = T.PRIMARY if on else T.TEXT_PRIMARY
                ctrl.update()
            except Exception:
                pass

        b.on_hover = _hover
        return b

    def _pick_dir(self, is_source: bool) -> None:
        # 通过 VaultGuard 自身的独立子进程运行原生 NSOpenPanel：既避免在 UI
        # 工作线程里直接碰 AppKit 导致卡顿/闪退，又让发起面板请求的进程 main
        # bundle 是已声明中文本地化的 VaultGuard.app，使系统面板显示中文。
        prompt = "选择源目录" if is_source else "选择目标目录"

        def work() -> None:
            from .dirpicker import pick_directory
            try:
                path = pick_directory(prompt)
            except Exception as e:  # noqa: BLE001
                self._handle_error(prompt, e)
                return
            if not path:
                return

            def apply_path() -> None:
                if is_source:
                    self.source_path = path
                    self.src_field.value = path
                else:
                    self.target_path = path
                    self.dst_field.value = path
                self.page.update()

            self._run_ui(apply_path)

        threading.Thread(target=work, daemon=True).start()

    # ========== 对比 + 续传检测 ==========
    def _do_compare(self) -> None:
        src = self.source_path.strip()
        dst = self.target_path.strip()
        if not src or not dst:
            self._snack("请先选择源目录和目标目录", error=True)
            return
        if not Path(src).is_dir():
            self._snack("源目录不存在", error=True)
            return
        if src == dst:
            self._snack("源目录与目标目录不能相同", error=True)
            return
        try:
            Path(dst).mkdir(parents=True, exist_ok=True)

            # 记住本次使用的目录，下次启动自动回填
            self.svc.settings.last_source = src
            self.svc.settings.last_target = dst
            self.svc.save_settings()

            resumable = self.svc.find_resumable(src, dst)
            if resumable:
                undone = self.svc.db.get_pending_items(
                    resumable["id"], only_undone=True)
                if undone:
                    self._show_resume_dialog(resumable["id"], len(undone), src, dst)
                    return
        except Exception as ex:  # noqa: BLE001
            self._handle_error("开始对比", ex)
            return

        self._run_compare(src, dst)

    def _run_compare(self, src: str, dst: str) -> None:
        self._task_stage = "comparing"
        self._compare_started_at = time.monotonic()
        self.cmp_pb_track = _progress_track(height=10)
        _set_progress_value(self.cmp_pb_track, 0)
        self.cmp_pct = ft.Text(
            "统计中", size=T.TEXT_28, weight=T.FW_MEDIUM,
            color=T.TEXT_TITLE, font_family=T.FONT_MONO)
        self.cmp_stat = ft.Text("正在统计文件数量 ...",
                                size=T.TEXT_13, color=T.TEXT_PRIMARY)
        self.cmp_eta = _mono_text("预计剩余 --", size=T.TEXT_13,
                                  color=T.TEXT_TERTIARY)
        self.cmp_file = ft.Text(
            "准备扫描 ...", size=T.TEXT_13, color=T.TEXT_PRIMARY,
            overflow=ft.TextOverflow.ELLIPSIS, font_family=T.FONT_MONO)

        self._set_task_content(ft.Column([
            self._page_header("正在对比"),
            ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
            _card(
                ft.Row([
                    ft.Column([
                        self.cmp_pct,
                        ft.Row([_badge("对比中", "running"), self.cmp_stat],
                               spacing=T.SP_2,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        self.cmp_eta,
                    ], spacing=T.SP_1, expand=True),
                ], vertical_alignment=ft.CrossAxisAlignment.START),
                ft.Container(height=T.SP_3),
                self.cmp_pb_track,
                ft.Row([
                    ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED,
                            size=14, color=T.TEXT_TERTIARY),
                    self.cmp_file,
                ], spacing=T.SP_2),
                padding=T.SP_8,
            ),
        ], spacing=T.SP_5))

        def progress_cb(prog: CompareProgress):
            # 仅写入最新快照，绝不在采集线程触碰 UI / page.update()
            self._latest_compare_prog = prog

        async def refresher():
            # 刷新协程跑在 page 的事件循环上：page.update() 在 loop 线程内执行，
            # put_nowait 能正常唤醒发送队列消费者，从而真正 flush 到客户端。
            # 固定 ~15fps 节流，避免高频更新冲垮 UI 管线。
            while self._compare_refreshing:
                self._render_compare_snapshot()
                await asyncio.sleep(1 / 15)
            # 退出前补最后一帧，确保最终状态落地
            self._render_compare_snapshot()

        def work():
            self._latest_compare_prog = None
            self._compare_refreshing = True
            # 在事件循环上启动刷新协程（关键：不能用裸线程，否则 update 不 flush）
            self._start_refresher(refresher, "对比进度刷新")
            try:
                diff = self.svc.compare(src, dst, progress_cb=progress_cb)
                self.current_diff = diff
                self._compare_refreshing = False
                self._run_ui(lambda: self._show_confirm(src, dst, diff))
            except Exception as ex:
                self._compare_refreshing = False
                self._handle_error("对比失败", ex)
                self._run_ui(self._show_home)

        threading.Thread(target=work, daemon=True).start()

    def _render_compare_snapshot(self) -> None:
        if self._task_stage != "comparing":
            return
        prog = self._latest_compare_prog
        if prog is None:
            return
        total = prog.total_files
        pct = (prog.processed_files / total) if total else 0.0

        if prog.phase == "scanning":
            elapsed = max(time.monotonic() - self._compare_started_at, 0.0)
            scan_pct = max(0.0, min(prog.progress_ratio, 1.0))
            _set_progress_value(self.cmp_pb_track, scan_pct)
            self.cmp_pct.value = f"统计 {scan_pct * 100:.0f}%"
            self.cmp_stat.value = f"已统计 {prog.processed_files} 个文件"
            self.cmp_eta.value = f"用时 {fmt_eta(elapsed)} · 剩余估算中"
        else:
            compare_pct = prog.progress_ratio if prog.progress_ratio else pct
            _set_progress_value(self.cmp_pb_track, compare_pct)
            self.cmp_pct.value = f"{compare_pct * 100:.0f}%"
            self.cmp_stat.value = f"{prog.processed_files}/{total} 文件"
            self.cmp_eta.value = f"预计剩余 {fmt_eta(prog.eta_seconds)}"

        if prog.finished:
            _set_progress_value(self.cmp_pb_track, 1.0)
            self.cmp_pct.value = "100%"
            self.cmp_eta.value = "预计剩余 0 秒"
        self.cmp_file.value = prog.current_file or "..."

        try:
            self.page.update()
        except Exception:
            pass

    def _show_resume_dialog(self, task_id: int, undone: int,
                            src: str, dst: str) -> None:
        def cont(e):
            self._close_overlay(dlg)
            self.current_task_id = task_id
            self._start_execution(src, dst, resume=True)

        def fresh(e):
            self._close_overlay(dlg)
            self._run_compare(src, dst)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("检测到未完成的备份任务",
                          weight=T.FW_MEDIUM, size=T.TEXT_16, color=T.TEXT_TITLE),
            content=ft.Text(
                f"任务 #{task_id} 还有 {undone} 个文件未完成。\n"
                "您可以从断点继续，或重新开始对比。",
                size=T.TEXT_14, color=T.TEXT_PRIMARY),
            shape=ft.RoundedRectangleBorder(radius=T.RADIUS_MD),
            actions=[
                _default_button("重新开始",
                                on_click=self._safe("重新开始", fresh)),
                _primary_button("从断点继续",
                                icon=ft.Icons.PLAY_ARROW_ROUNDED,
                                on_click=self._safe("从断点继续", cont)),
            ],
        )
        self._open_overlay(dlg)

    # ========== 确认页 ==========
    # 排序维度：键 -> (标签, 取值函数, 默认是否升序)
    _CF_SORT_DEFS = [
        ("name", "名称", lambda it: it.rel_path.lower(), True),
        ("size", "文件容量", lambda it: it.size, False),
        ("type", "类型", lambda it: Path(it.rel_path).suffix.lower(), True),
        ("date", "日期", lambda it: it.src_mtime, False),
    ]

    def _show_confirm(self, src: str, dst: str, diff: DiffResult) -> None:
        self._task_stage = "confirm"
        # 确认页状态：清单副本、勾选集合（默认全选）、排序维度与方向
        self._cf_src = src
        self._cf_dst = dst
        self._cf_diff = diff
        self._cf_items = list(diff.pending_items)
        self._cf_selected = {id(it) for it in self._cf_items}
        self._cf_sort_key = "name"
        self._cf_sort_asc = True

        # 顶部统计值随勾选动态更新
        self._cf_stat_new = ft.Text(
            str(diff.new_count), size=T.TEXT_28, weight=T.FW_MEDIUM,
            color=T.SUCCESS, font_family=T.FONT_MONO)
        self._cf_stat_upd = ft.Text(
            str(diff.updated_count), size=T.TEXT_28, weight=T.FW_MEDIUM,
            color=T.WARNING, font_family=T.FONT_MONO)
        self._cf_stat_bytes = ft.Text(
            fmt_size(diff.pending_bytes), size=T.TEXT_28, weight=T.FW_MEDIUM,
            color=T.PRIMARY, font_family=T.FONT_MONO)

        def stat_cell(value_ctrl, label, color, icon):
            return ft.Container(
                content=ft.Column([
                    ft.Row([ft.Icon(icon, color=color, size=16), value_ctrl],
                           spacing=T.SP_2, tight=True,
                           alignment=ft.MainAxisAlignment.CENTER),
                    _muted_text(label, size=T.TEXT_12),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=T.SP_1),
                expand=True, alignment=ft.Alignment.CENTER,
                padding=T.SP_3,
            )

        def vline():
            return ft.Container(width=1, bgcolor=T.BORDER, height=44)

        # 全选框 + 已选计数 + 右上角排序 tab
        self._cf_select_all = ft.Checkbox(
            value=True, tristate=True, active_color=T.PRIMARY,
            on_change=self._safe("全选切换", lambda e: self._cf_toggle_all()))
        self._cf_count_text = _muted_text("", size=T.TEXT_13)
        self._cf_tab_holder = ft.Container(content=self._cf_sort_tab())
        toolbar = ft.Container(
            content=ft.Row([
                ft.Row([self._cf_select_all,
                        ft.Text("全选", size=T.TEXT_13, color=T.TEXT_PRIMARY,
                                weight=T.FW_MEDIUM),
                        self._cf_count_text],
                       spacing=T.SP_2,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self._cf_tab_holder,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=T.SP_2, horizontal=T.SP_4),
            border=ft.Border(bottom=ft.BorderSide(1, T.BORDER)),
        )

        self._cf_list_holder = ft.Container(
            content=self._cf_build_listview(), expand=True)

        self._cf_confirm_holder = ft.Container(content=self._cf_confirm_btn())
        back_btn = _default_button("返回",
                                   icon=ft.Icons.ARROW_BACK_ROUNDED,
                                   on_click=self._safe(
                                       "返回任务页",
                                       lambda e: self._reset_task_home()))

        self._set_task_content(ft.Column([
            self._page_header("待备份清单", f"{src}  →  {dst}"),
            ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
            _card(
                ft.Row([
                    stat_cell(self._cf_stat_new, "新增", T.SUCCESS,
                              ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED),
                    vline(),
                    stat_cell(self._cf_stat_upd, "更新", T.WARNING,
                              ft.Icons.AUTORENEW_ROUNDED),
                    vline(),
                    stat_cell(ft.Text(str(diff.skipped_count), size=T.TEXT_28,
                                      weight=T.FW_MEDIUM, color=T.TEXT_TERTIARY,
                                      font_family=T.FONT_MONO),
                              "跳过", T.TEXT_TERTIARY,
                              ft.Icons.SKIP_NEXT_ROUNDED),
                    vline(),
                    stat_cell(self._cf_stat_bytes, "预计传输", T.PRIMARY,
                              ft.Icons.UPLOAD_OUTLINED),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ),
            ft.Container(
                content=ft.Column([toolbar, self._cf_list_holder],
                                  spacing=0, expand=True),
                bgcolor=T.BG,
                border_radius=T.RADIUS_MD,
                border=ft.Border.all(1, T.BORDER),
                expand=True,
            ),
            ft.Row([back_btn, self._cf_confirm_holder],
                   alignment=ft.MainAxisAlignment.END,
                   spacing=T.SP_3),
        ], spacing=T.SP_5, expand=True))

        self._cf_sync_meta(update=False)

    # ---------- 确认页：排序 tab ----------
    def _cf_sort_tab(self) -> ft.Row:
        chips = [self._cf_sort_chip(key, label)
                 for key, label, _fn, _asc in self._CF_SORT_DEFS]
        return ft.Row([
            _muted_text("排序", size=T.TEXT_12),
            *chips,
        ], spacing=T.SP_1, tight=True,
           vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _cf_sort_chip(self, key: str, label: str) -> ft.Container:
        active = key == self._cf_sort_key
        fg = T.PRIMARY if active else T.TEXT_PRIMARY
        children = [ft.Text(label, size=T.TEXT_13, color=fg,
                            weight=T.FW_MEDIUM)]
        if active:
            children.append(ft.Icon(
                ft.Icons.ARROW_UPWARD_ROUNDED if self._cf_sort_asc
                else ft.Icons.ARROW_DOWNWARD_ROUNDED,
                size=14, color=fg))
        chip = ft.Container(
            content=ft.Row(children, spacing=T.SP_1, tight=True),
            bgcolor=T.PRIMARY_BG if active else T.BG,
            border=ft.Border.all(1, T.PRIMARY if active else T.BORDER),
            border_radius=T.RADIUS,
            padding=ft.Padding.symmetric(vertical=0, horizontal=T.SP_3),
            height=30,
            alignment=ft.Alignment.CENTER,
            animate=ft.Animation(T.DUR_FAST, T.EASE),
            on_click=self._safe(f"排序：{label}",
                                lambda e, k=key: self._cf_set_sort(k)),
        )

        def _hover(e: ft.HoverEvent, c=chip, a=active) -> None:
            try:
                if a:
                    return
                c.border = ft.Border.all(
                    1, T.PRIMARY if e.data == "true" else T.BORDER)
                c.update()
            except Exception:
                pass

        chip.on_hover = _hover
        return chip

    def _cf_set_sort(self, key: str) -> None:
        if key == self._cf_sort_key:
            self._cf_sort_asc = not self._cf_sort_asc
        else:
            self._cf_sort_key = key
            default_asc = next(asc for k, _l, _fn, asc in self._CF_SORT_DEFS
                               if k == key)
            self._cf_sort_asc = default_asc
        self._cf_tab_holder.content = self._cf_sort_tab()
        self._cf_list_holder.content = self._cf_build_listview()
        self.page.update()

    def _cf_apply_sort(self) -> None:
        fn = next(f for k, _l, f, _a in self._CF_SORT_DEFS
                  if k == self._cf_sort_key)
        self._cf_items.sort(key=fn, reverse=not self._cf_sort_asc)

    # ---------- 确认页：列表与勾选 ----------
    def _cf_build_listview(self):
        self._cf_apply_sort()
        items = self._cf_items
        if not items:
            return ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED,
                            color=T.SUCCESS, size=40),
                    ft.Text("没有需要备份的文件", weight=T.FW_MEDIUM,
                            color=T.TEXT_TITLE, size=T.TEXT_16),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                   spacing=T.SP_2),
                padding=T.SP_8,
                alignment=ft.Alignment.CENTER,
            )
        rows = [self._cf_row(it) for it in items[:500]]
        if len(items) > 500:
            rows.append(ft.Container(
                content=_muted_text(
                    f"... 以及另外 {len(items) - 500} 个文件（默认随全选一并备份）",
                    size=T.TEXT_12),
                padding=ft.Padding.symmetric(vertical=8, horizontal=T.SP_4)))
        return ft.ListView(rows, spacing=0, expand=True)

    def _cf_row(self, it) -> ft.Container:
        iid = id(it)
        kind = "success" if it.action.value == "new" else "warning"
        cb = ft.Checkbox(
            value=iid in self._cf_selected, active_color=T.PRIMARY,
            on_change=self._safe(
                "选择备份文件",
                lambda e, k=iid: self._cf_toggle(k, e.control.value)))
        return ft.Container(
            content=ft.Row([
                cb,
                _badge(it.action.value, kind),
                ft.Text(it.rel_path, size=T.TEXT_13, expand=True,
                        color=T.TEXT_TITLE, font_family=T.FONT_MONO,
                        overflow=ft.TextOverflow.ELLIPSIS),
                _mono_text(fmt_size(it.size), size=T.TEXT_12,
                           color=T.TEXT_TERTIARY),
            ], spacing=T.SP_3,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=4, horizontal=T.SP_4),
            border=ft.Border(bottom=ft.BorderSide(1, T.BORDER_LIGHT)),
        )

    def _cf_toggle(self, iid: int, value: bool) -> None:
        if value:
            self._cf_selected.add(iid)
        else:
            self._cf_selected.discard(iid)
        self._cf_sync_meta()

    def _cf_toggle_all(self) -> None:
        if len(self._cf_selected) >= len(self._cf_items):
            self._cf_selected = set()
        else:
            self._cf_selected = {id(it) for it in self._cf_items}
        self._cf_list_holder.content = self._cf_build_listview()
        self._cf_sync_meta()

    def _cf_sync_meta(self, update: bool = True) -> None:
        n = len(self._cf_selected)
        m = len(self._cf_items)
        self._cf_select_all.value = (
            True if n == m and m > 0 else (False if n == 0 else None))
        self._cf_count_text.value = f"已选 {n} / {m}"
        sel_new = sum(1 for it in self._cf_diff.new_items
                      if id(it) in self._cf_selected)
        sel_upd = sum(1 for it in self._cf_diff.updated_items
                      if id(it) in self._cf_selected)
        sel_bytes = sum(it.size for it in self._cf_items
                        if id(it) in self._cf_selected)
        self._cf_stat_new.value = str(sel_new)
        self._cf_stat_upd.value = str(sel_upd)
        self._cf_stat_bytes.value = fmt_size(sel_bytes)
        self._cf_confirm_holder.content = self._cf_confirm_btn()
        if update:
            self.page.update()

    def _cf_confirm_btn(self) -> ft.Container:
        return _primary_button(
            "确认备份", icon=ft.Icons.PLAY_ARROW_ROUNDED,
            disabled=not self._cf_selected,
            on_click=self._safe("确认备份", lambda e: self._cf_do_backup()),
        )

    def _cf_do_backup(self) -> None:
        sel = self._cf_selected
        if not sel:
            return
        diff = self._cf_diff
        filtered = DiffResult(
            new_items=[it for it in diff.new_items if id(it) in sel],
            updated_items=[it for it in diff.updated_items if id(it) in sel],
            skipped_items=diff.skipped_items,
        )
        self._confirm_backup(self._cf_src, self._cf_dst, filtered)

    def _confirm_backup(self, src: str, dst: str, diff: DiffResult) -> None:
        try:
            task_id = self.svc.create_task(src, dst, diff)
            self.current_task_id = task_id
            self._start_execution(src, dst, resume=False)
        except Exception as ex:  # noqa: BLE001
            self._handle_error("创建备份任务", ex)

    # ========== 任务进行页 ==========
    def _show_progress_view(self) -> None:
        self._task_stage = "backup"
        # 纯色进度条：track + fill，靠真实 width 推进，不做装饰动画
        self.pb_track = ft.Container(
            bgcolor=T.FILL,
            height=6,
            border_radius=T.RADIUS_SM,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            expand=True,
        )
        self.pb_fill = ft.Container(
            bgcolor=T.PRIMARY,
            border_radius=T.RADIUS_SM,
            height=6,
            width=0,
            animate=ft.Animation(T.DUR_BASE, T.EASE),
        )
        self.pb_track.content = ft.Row([self.pb_fill], spacing=0)

        self.lbl_pct = ft.Text(
            "0%", size=T.TEXT_28, weight=T.FW_MEDIUM,
            color=T.TEXT_TITLE, font_family=T.FONT_MONO)
        self.lbl_file = ft.Text(
            "准备中 ...", size=T.TEXT_13, color=T.TEXT_PRIMARY,
            overflow=ft.TextOverflow.ELLIPSIS, font_family=T.FONT_MONO)
        self.lbl_stat = ft.Text("", size=T.TEXT_13, color=T.TEXT_PRIMARY)
        self.lbl_speed = _mono_text("", size=T.TEXT_13, color=T.TEXT_TERTIARY)
        self.log_view = ft.ListView([], spacing=2, expand=True,
                                    padding=T.SP_3, auto_scroll=True)

        self.btn_pause = _default_button(
            "暂停", icon=ft.Icons.PAUSE_ROUNDED,
            on_click=self._safe("暂停/继续", lambda e: self._toggle_pause()))
        self.btn_cancel = _default_button(
            "中断", icon=ft.Icons.STOP_ROUNDED,
            on_click=self._safe("中断备份", lambda e: self._cancel_task()),
            danger=True)

        self._set_task_content(ft.Column([
            self._page_header("备份进行中"),
            ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
            _card(
                ft.Row([
                    ft.Column([
                        self.lbl_pct,
                        ft.Row([_badge("备份中", "running"), self.lbl_stat],
                               spacing=T.SP_2,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        self.lbl_speed,
                    ], spacing=T.SP_1, expand=True),
                    ft.Row([self.btn_pause, self.btn_cancel],
                           spacing=T.SP_2),
                ], vertical_alignment=ft.CrossAxisAlignment.START),
                ft.Container(height=T.SP_2),
                self.pb_track,
                ft.Row([
                    ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED,
                            size=14, color=T.TEXT_TERTIARY),
                    self.lbl_file,
                ], spacing=T.SP_2),
            ),
            _section_title("实时日志"),
            ft.Container(
                content=self.log_view,
                bgcolor=T.FILL,
                border_radius=T.RADIUS_MD,
                border=ft.Border.all(1, T.BORDER),
                padding=T.SP_2,
                expand=True,
            ),
        ], spacing=T.SP_5, expand=True))

    def _start_execution(self, src: str, dst: str, resume: bool) -> None:
        self._show_progress_view()
        self._running = True
        self.executor = self.svc.make_executor()
        task_id = self.current_task_id

        def progress_cb(prog: CopyProgress):
            self._latest_copy_prog = prog

        async def refresher():
            while self._copy_refreshing:
                self._update_progress()
                await asyncio.sleep(1 / 15)
            self._update_progress()

        def work():
            self._latest_copy_prog = None
            self._last_log_file = ""
            self._copy_refreshing = True
            self._start_refresher(refresher, "备份进度刷新")
            try:
                from vaultguard.core.executor import cleanup_temp_files
                cleanup_temp_files(dst)
                prog = self.executor.run(task_id, src, dst, resume=resume,
                                         progress_cb=progress_cb)
                try:
                    self.svc._write_text_log(task_id, src, dst, prog)
                except Exception as log_ex:  # noqa: BLE001
                    self._record_error("写入备份日志失败", log_ex)
                self._running = False
                self._copy_refreshing = False
                self._run_ui(lambda: self._on_finished(prog))
            except Exception as ex:
                self._running = False
                self._copy_refreshing = False
                self._handle_error("执行备份", ex)

        threading.Thread(target=work, daemon=True).start()

    def _update_progress(self) -> None:
        prog = self._latest_copy_prog
        if prog is None:
            return
        pct = (prog.transferred_bytes / prog.total_bytes) if prog.total_bytes else 1.0
        # 纯色填充，靠父 Row 的 expand 比例近似真实 width 推进
        if pct < 1.0:
            spacer_expand = max(1.0 - pct, 0.001)
            self.pb_track.content = ft.Row([
                ft.Container(bgcolor=T.PRIMARY, height=6,
                             expand=max(pct, 0.001),
                             border_radius=T.RADIUS_SM),
                ft.Container(expand=spacer_expand),
            ], spacing=0)
        else:
            self.pb_track.content = ft.Container(
                bgcolor=T.PRIMARY, height=6, expand=True,
                border_radius=T.RADIUS_SM)

        self.lbl_pct.value = f"{pct * 100:.0f}%"
        self.lbl_stat.value = (
            f"{prog.processed_files}/{prog.total_files} 文件 · "
            f"复制 {prog.copied} · 失败 {prog.failed}")
        self.lbl_speed.value = (
            f"{fmt_size(prog.speed_bps)}/s · 剩余 {fmt_eta(prog.eta_seconds)}")
        self.lbl_file.value = prog.current_file or "..."

        if prog.current_file and prog.current_file != self._last_log_file:
            self._last_log_file = prog.current_file
            self.log_view.controls.append(
                ft.Text(f"✓ {prog.current_file}", size=T.TEXT_12,
                        color=T.TEXT_PRIMARY, font_family=T.FONT_MONO))
            if len(self.log_view.controls) > 1000:
                self.log_view.controls.pop(0)
        try:
            self.page.update()
        except Exception:
            pass

    def _toggle_pause(self) -> None:
        if not self.executor:
            return
        row = self.btn_pause.content
        icon_ctrl, label_ctrl = row.controls[0], row.controls[1]
        if self.executor.is_paused:
            self.executor.resume()
            label_ctrl.value = "暂停"
            icon_ctrl.name = ft.Icons.PAUSE_ROUNDED
        else:
            self.executor.pause()
            label_ctrl.value = "继续"
            icon_ctrl.name = ft.Icons.PLAY_ARROW_ROUNDED
        self.page.update()

    def _cancel_task(self) -> None:
        if self.executor:
            self.executor.cancel()
            self.btn_cancel.on_click = None
            self._snack("已请求中断，断点已保存，可稍后从断点继续")

    def _on_finished(self, prog: CopyProgress) -> None:
        if prog.finished:
            msg = (f"备份完成：复制 {prog.copied}，失败 {prog.failed}，"
                   f"共 {prog.total_files} 个文件。")
            self._snack(msg, error=prog.failed > 0)
        self._show_result(prog)

    def _show_result(self, prog: CopyProgress) -> None:
        self._task_stage = "result"
        success = prog.finished and prog.failed == 0
        if success:
            kind, color, bg, icon = ("success", T.SUCCESS, T.SUCCESS_BG,
                                     ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED)
            title = "备份完成"
        elif prog.finished:
            kind, color, bg, icon = ("warning", T.WARNING, T.WARNING_BG,
                                     ft.Icons.WARNING_AMBER_ROUNDED)
            title = "备份完成（有失败项）"
        else:
            kind, color, bg, icon = ("danger", T.DANGER, T.DANGER_BG,
                                     ft.Icons.STOP_CIRCLE_OUTLINED)
            title = "任务已中断"

        big_icon = ft.Container(
            width=56, height=56,
            border_radius=T.RADIUS_MD,
            bgcolor=bg,
            content=ft.Icon(icon, size=28, color=color),
            alignment=ft.Alignment.CENTER,
        )

        def kv(label, value, mono=True):
            return ft.Row([
                _muted_text(label, size=T.TEXT_13),
                ft.Container(expand=True),
                (_mono_text(str(value), size=T.TEXT_13, color=T.TEXT_TITLE)
                 if mono else
                 ft.Text(str(value), size=T.TEXT_13,
                         color=T.TEXT_TITLE, weight=T.FW_MEDIUM)),
            ])

        self._set_task_content(ft.Column([
            self._page_header("备份结果"),
            ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
            _card(
                ft.Row([
                    big_icon,
                    ft.Column([
                        ft.Text(title, size=T.TEXT_20, weight=T.FW_MEDIUM,
                                color=T.TEXT_TITLE),
                        _badge({"success": "成功", "warning": "完成（有失败）",
                                "danger": "已中断"}[kind], kind),
                    ], spacing=T.SP_2),
                ], spacing=T.SP_4,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(color=T.BORDER_LIGHT, height=1),
                kv("复制", f"{prog.copied} 个"),
                kv("失败", f"{prog.failed} 个"),
                kv("传输", fmt_size(prog.transferred_bytes)),
                ft.Container(height=T.SP_2),
                ft.Row([
                    _default_button("返回任务",
                                    icon=ft.Icons.HOME_OUTLINED,
                                    on_click=self._safe(
                                        "返回任务", lambda e: self._goto_home())),
                    _primary_button("查看历史",
                                    icon=ft.Icons.HISTORY_ROUNDED,
                                    on_click=self._safe(
                                        "查看历史", lambda e: self._goto_history())),
                ], alignment=ft.MainAxisAlignment.END,
                   spacing=T.SP_3),
            ),
        ], spacing=T.SP_5))

    def _goto_home(self) -> None:
        self._nav_index = 0
        self._refresh_nav()
        self._reset_task_home()

    def _goto_history(self) -> None:
        self._nav_index = 1
        self._refresh_nav()
        self._show_history()

    # ========== 历史记录页 ==========
    def _show_history(self) -> None:
        try:
            tasks = self.svc.list_tasks()
        except Exception as ex:  # noqa: BLE001
            self._handle_error("加载历史记录", ex)
            return
        if not tasks:
            self._set_content(ft.Column([
                self._page_header("历史记录"),
                ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
                _card(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.INBOX_OUTLINED,
                                    color=T.TEXT_TERTIARY, size=40),
                            _muted_text("暂无历史任务", size=T.TEXT_13),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                           spacing=T.SP_2),
                        padding=T.SP_8,
                        alignment=ft.Alignment.CENTER,
                    ),
                ),
            ], spacing=T.SP_5))
            return

        kind_map = {
            "completed": "success",
            "failed": "danger",
            "paused": "warning",
            "running": "running",
            "cancelled": "warning",
        }

        def cell(control, *, width: Optional[int] = None,
                 expand: Optional[int] = None,
                 align=ft.Alignment.CENTER_LEFT) -> ft.Container:
            return ft.Container(
                content=control,
                width=width,
                expand=expand,
                alignment=align,
                padding=ft.Padding.symmetric(horizontal=T.SP_3, vertical=0),
            )

        def head(label: str, *, width: Optional[int] = None,
                 expand: Optional[int] = None,
                 align=ft.Alignment.CENTER_LEFT) -> ft.Container:
            return cell(
                ft.Text(label, size=T.TEXT_12, color=T.TEXT_TERTIARY,
                        weight=T.FW_MEDIUM, overflow=ft.TextOverflow.ELLIPSIS),
                width=width,
                expand=expand,
                align=align,
            )

        def table_row(t: dict, *, last: bool = False) -> ft.Container:
            kind = kind_map.get(t["status"], "running")
            failed_color = T.DANGER if t["failed_files"] else T.TEXT_TERTIARY
            detail_btn = ft.IconButton(
                    icon=ft.Icons.ARTICLE_OUTLINED,
                    icon_color=T.PRIMARY,
                    icon_size=18,
                    width=32,
                    height=32,
                    tooltip="查看详情",
                    on_click=self._safe(
                        "查看任务详情",
                        lambda e, tid=t["id"]: self._show_task_detail(tid)))
            return ft.Container(
                content=ft.Row([
                    cell(_mono_text(f"#{t['id']}", size=T.TEXT_13,
                                    color=T.TEXT_TITLE), width=70),
                    cell(_badge(t["status"], kind), expand=2),
                    cell(_mono_text(str(t["copied_files"]), color=T.SUCCESS),
                         width=82),
                    cell(_mono_text(str(t["failed_files"]), color=failed_color),
                         width=82),
                    cell(ft.Text(fmt_time(t["start_time"]), size=T.TEXT_13,
                                 color=T.TEXT_PRIMARY,
                                 overflow=ft.TextOverflow.ELLIPSIS),
                         expand=3),
                    cell(detail_btn, width=70, align=ft.Alignment.CENTER),
                ], spacing=0, expand=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                height=58,
                border=None if last else ft.Border(
                    bottom=ft.BorderSide(1, T.BORDER)),
            )

        table_header = ft.Container(
            content=ft.Row([
                head("ID", width=70),
                head("状态", expand=2),
                head("复制", width=82),
                head("失败", width=82),
                head("开始时间", expand=3),
                head("详情", width=70, align=ft.Alignment.CENTER),
            ], spacing=0, expand=True,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=42,
            bgcolor=T.FILL,
            border=ft.Border(bottom=ft.BorderSide(1, T.BORDER)),
        )
        row_controls = [
            table_row(t, last=i == len(tasks) - 1)
            for i, t in enumerate(tasks)
        ]
        table = ft.Column([
            table_header,
            ft.ListView(row_controls, spacing=0, expand=True, padding=0),
        ], spacing=0, expand=True)
        history_panel = ft.Container(
            content=table,
            bgcolor=T.BG,
            border_radius=T.RADIUS_MD,
            border=ft.Border.all(1, T.BORDER),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            expand=True,
        )
        self._set_content(ft.Column([
            self._page_header("历史记录", f"共 {len(tasks)} 条任务记录"),
            ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
            history_panel,
        ], spacing=T.SP_5, expand=True))

    def _show_task_detail(self, task_id: int) -> None:
        try:
            logs = self.svc.get_file_logs(task_id)
            task = self.svc.db.get_task(task_id)
        except Exception as ex:  # noqa: BLE001
            self._handle_error("加载任务详情", ex)
            return
        items = []
        for lg in logs:
            ok = lg["action"] != "fail"
            items.append(ft.Row([
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED if ok
                    else ft.Icons.ERROR_OUTLINE_ROUNDED,
                    size=14,
                    color=T.SUCCESS if ok else T.DANGER),
                ft.Text(lg["file_path"], size=T.TEXT_13, expand=True,
                        color=T.TEXT_PRIMARY, font_family=T.FONT_MONO,
                        overflow=ft.TextOverflow.ELLIPSIS),
                _muted_text(lg["reason"], size=T.TEXT_12),
            ], spacing=T.SP_2))
        if not items:
            items = [_muted_text("无文件日志")]

        content = ft.Container(
            content=ft.ListView(items, spacing=T.SP_1, padding=T.SP_3),
            width=680, height=440,
        )
        dlg = ft.AlertDialog(
            title=ft.Text(
                f"任务 #{task_id} 详情"
                + (f" · {task['status']}" if task else ""),
                weight=T.FW_MEDIUM, size=T.TEXT_16, color=T.TEXT_TITLE),
            content=content,
            shape=ft.RoundedRectangleBorder(radius=T.RADIUS_MD),
            actions=[_default_button(
                "关闭", on_click=self._safe(
                    "关闭任务详情", lambda e: self._close_overlay(dlg)))],
        )
        self._open_overlay(dlg)

    # ========== 设置页 ==========
    def _show_settings(self) -> None:
        s = self.svc.settings

        def _tf(label, value, **kw) -> ft.TextField:
            return ft.TextField(
                label=label, value=value,
                border_radius=T.RADIUS,
                border_color=T.BORDER,
                focused_border_color=T.PRIMARY,
                cursor_color=T.PRIMARY,
                text_size=T.TEXT_14,
                content_padding=ft.Padding.symmetric(vertical=8, horizontal=12),
                **kw,
            )

        self.f_tolerance = _tf(
            "mtime 容差（秒）", str(s.mtime_tolerance),
            width=220, dense=True,
            keyboard_type=ft.KeyboardType.NUMBER)
        self.f_compare_size = ft.Switch(
            label="检测文件容量变化", value=s.compare_size,
            active_color=T.PRIMARY)
        self.f_verify_hash = ft.Switch(
            label="Hash 校验",
            value=s.verify_hash, active_color=T.PRIMARY)
        self.f_delete_sync = ft.Switch(
            label="删除同步",
            value=s.delete_sync, active_color=T.DANGER)
        self.f_use_recycle = ft.Switch(
            label="移入回收区",
            value=s.use_recycle, active_color=T.PRIMARY)
        self.f_exclude = _tf(
            "排除规则（每行一个，支持通配符）",
            "\n".join(s.exclude_patterns),
            multiline=True, min_lines=3, max_lines=8)
        self.f_retry = _tf(
            "单文件失败重试次数", str(s.retry_times),
            width=220, dense=True,
            keyboard_type=ft.KeyboardType.NUMBER)

        data_dir_row = ft.Row([
            ft.Icon(ft.Icons.FOLDER_SHARED_OUTLINED,
                    color=T.TEXT_TERTIARY, size=18),
            _muted_text(f"数据/日志/配置位置：{self.svc.data_dir}",
                        size=T.TEXT_12),
        ], spacing=T.SP_2)

        save_btn = _primary_button(
            "保存设置", icon=ft.Icons.SAVE_OUTLINED,
            on_click=self._safe("保存设置", lambda e: self._save_settings()))
        has_error_report = self.error_reporter.load_latest() is not None
        report_btn = _default_button(
            "发送最近错误", icon=ft.Icons.EMAIL_OUTLINED,
            on_click=self._safe(
                "发送最近错误", lambda e: self._send_error_report()),
            disabled=not has_error_report,
            tooltip=(None if has_error_report else "最近没有报错需要提交"))

        self._set_content(ft.Column([
            self._page_header("设置"),
            ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
            ft.Container(
                content=ft.Column([
                    _card(
                        _section_title("对比策略"),
                        self.f_tolerance,
                        self.f_compare_size,
                    ),
                    _card(
                        _section_title("文件安全"),
                        self.f_verify_hash,
                        self.f_retry,
                        ft.Divider(color=T.BORDER_LIGHT, height=1),
                        ft.Row([
                            ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED,
                                    color=T.DANGER, size=16),
                            ft.Text("删除策略",
                                    size=T.TEXT_14, weight=T.FW_MEDIUM,
                                    color=T.DANGER),
                        ], spacing=T.SP_2),
                        self.f_delete_sync,
                        self.f_use_recycle,
                    ),
                    _card(
                        _section_title("排除规则"),
                        self.f_exclude,
                    ),
                    _card(
                        _section_title("错误反馈"),
                        data_dir_row,
                        _muted_text(
                            f"异常会自动记录到 {self.error_reporter.report_dir}",
                            size=T.TEXT_12),
                        ft.Row([report_btn], alignment=ft.MainAxisAlignment.END),
                    ),
                    ft.Row([save_btn], alignment=ft.MainAxisAlignment.END),
                ], spacing=T.SP_4),
                width=640,
            ),
        ], spacing=T.SP_5, scroll=ft.ScrollMode.AUTO))

    def _save_settings(self) -> None:
        s = self.svc.settings
        try:
            s.mtime_tolerance = float(self.f_tolerance.value)
            s.retry_times = int(self.f_retry.value)
        except ValueError:
            self._snack("容差与重试次数必须是数字", error=True)
            return
        s.compare_size = self.f_compare_size.value
        s.verify_hash = self.f_verify_hash.value
        s.delete_sync = self.f_delete_sync.value
        s.use_recycle = self.f_use_recycle.value
        s.exclude_patterns = [p.strip() for p in self.f_exclude.value.splitlines()
                              if p.strip()]
        try:
            self.svc.save_settings()
            self._snack("设置已保存")
        except Exception as ex:  # noqa: BLE001
            self._handle_error("保存设置", ex)


def main(page: ft.Page) -> None:
    VaultGuardApp(page)


def run() -> None:
    """纯桌面软件：始终使用原生窗口运行。"""
    import os
    import sys

    # 子进程模式：仅弹出原生目录选择器后退出，不启动主窗口。
    # 该子进程的 main bundle 即 VaultGuard.app（已声明中文本地化），系统
    # 原生面板会跟随系统语言显示中文。
    if os.environ.get("VAULTGUARD_DIR_PICKER") == "1":
        from .dirpicker import run_picker_process
        run_picker_process()
        return

    # 打包成 .app 后，优先使用随包内置、且已改名为 VaultGuard 的窗口客户端，
    # 使应用完全自包含、Dock 显示名为 VaultGuard，且不依赖全局缓存。
    if getattr(sys, "frozen", False):
        resources = os.path.join(
            os.path.dirname(os.path.dirname(sys.executable)), "Resources")
        client_dir = os.path.join(resources, "client")
        if os.path.isdir(client_dir):
            os.environ[VIEW_PATH_ENV] = client_dir

    ft.app(target=main)


if __name__ == "__main__":
    run()
