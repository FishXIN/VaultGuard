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
import sys
import threading
import time
import unicodedata
import webbrowser
from pathlib import Path
from typing import Callable, Optional

from vaultguard import __version__
from vaultguard.core.models import CompareProgress, CopyProgress, DiffResult
from vaultguard.core.service import BackupService
from . import tokens as T
from .error_reporter import ErrorReporter
from .helpers import fmt_eta, fmt_relative_time, fmt_size
from .runtime import VIEW_PATH_ENV, ft

# 平台判定：macOS 采用无边框（隐藏标题栏）的无缝侧栏风格；Windows/Linux 保留
# 系统原生标题栏，以提供最小化 / 最大化 / 关闭三个窗口按钮。
_IS_MACOS = sys.platform == "darwin"


def _bundled_icon_path() -> Optional[str]:
    """返回随包打入的 Windows 窗口图标（assets/icon.ico）的绝对路径。

    打包后（PyInstaller onedir）资源解包在 sys._MEIPASS/assets 下；
    开发态则取仓库根目录 assets/。找不到时返回 None。
    """
    candidates = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(Path(base) / "assets" / "icon.ico")
    candidates.append(Path(__file__).resolve().parents[2] / "assets" / "icon.ico")
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


def _bundled_font_path() -> Optional[str]:
    """返回随包打入的思源黑体（assets/fonts/NotoSansSC.ttf）的绝对路径。

    打包后（PyInstaller onedir）资源解包在 sys._MEIPASS/assets 下；
    开发态则取仓库根目录 assets/。找不到时返回 None（回退系统字体）。

    注意：page.fonts 接受本地绝对路径或 URL，这里直接给绝对路径，
    无需依赖 flet 的 assets_dir 机制，跨打包形态更稳妥。
    """
    candidates = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(Path(base) / "assets" / "fonts" / "NotoSansSC.ttf")
    candidates.append(
        Path(__file__).resolve().parents[2] / "assets" / "fonts" / "NotoSansSC.ttf"
    )
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


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
# 目录选择按钮（assets/Icon/Contents.svg：打开的文件夹/内容图标）
_NAV_SVG_FOLDER = (
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<path d="M3 5.64V4.2C3 3.54 3.45 3 4 3H6.3C6.54 3 6.78 3.108 6.96 3.312L8 '
    '4.56H12C12.55 4.56 13 5.1 13 5.76V6" stroke="#0B0B0F" stroke-linecap="round" '
    'stroke-linejoin="round"/>'
    '<path d="M3 8C3 7.45 3.45 7 4 7H12C12.55 7 13 7.45 13 8V11.8C13 12.35 12.55 '
    '12.8 12 12.8H4C3.45 12.8 3 12.35 3 11.8V8Z" stroke="#0B0B0F" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>'
)
# 文档图标（assets/Icon/Document.svg：单页文档线性图标）—— 历史记录"详情"按钮
_NAV_SVG_DOCUMENT = (
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<path d="M4.5 1.5H9L12.5 5V13.5C12.5 14.05 12.05 14.5 11.5 14.5H4.5C3.95 '
    '14.5 3.5 14.05 3.5 13.5V2.5C3.5 1.95 3.95 1.5 4.5 1.5Z" stroke="#0B0B0F" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M9 1.5V4C9 4.55 9.45 5 10 5H12.5" stroke="#0B0B0F" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
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
    text_units = sum(
        2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        for ch in label
    )
    badge_width = max(46, min(116, text_units * 6 + 22))
    return ft.Container(
        content=ft.Row([
            ft.Container(width=6, height=6, bgcolor=fg, border_radius=3),
            ft.Text(label, size=T.TEXT_12, weight=T.FW_MEDIUM, color=fg),
        ], spacing=T.SP_1, tight=True),
        width=badge_width,
        bgcolor=bg,
        border_radius=T.RADIUS_SM,
        padding=ft.Padding.symmetric(vertical=0, horizontal=T.SP_1),
        height=22,
        alignment=ft.Alignment.CENTER,
    )


def _task_status_label(status: str) -> str:
    """将任务内部状态转换为界面展示文案。"""
    return {
        "pending": "等待中",
        "running": "传输中",
        "paused": "已暂停",
        "completed": "已完成",
        "failed": "出错了",
        "cancelled": "已取消",
    }.get(status, status)


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


def _detail_summary_chip(icon, color: str, label: str, count: int) -> ft.Container:
    """详情页头部摘要徽标：复制 / 删除 / 失败 数量。"""
    bg_map = {T.SUCCESS: T.SUCCESS_BG, T.DANGER: T.DANGER_BG,
              T.WARNING: T.WARNING_BG}
    return ft.Container(
        content=ft.Row([
            ft.Icon(icon, size=14, color=color),
            ft.Text(label, size=T.TEXT_12, color=T.TEXT_PRIMARY,
                    weight=T.FW_MEDIUM),
            ft.Text(str(count), size=T.TEXT_13, color=color,
                    font_family=T.FONT_MONO, weight=T.FW_MEDIUM),
        ], spacing=T.SP_2,
           vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor=bg_map.get(color, T.FILL),
        padding=ft.Padding.symmetric(vertical=4, horizontal=10),
        border_radius=T.RADIUS,
    )


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
        self._task_status_slot: Optional[ft.Container] = None
        self._task_stage = "home"
        self._task_content = None
        self._compare_started_at = 0.0
        # 数据采集与界面刷新解耦：扫描线程只写快照，由独立节流线程统一重绘
        self._latest_compare_prog: Optional[CompareProgress] = None
        self._compare_refreshing = False
        self._latest_copy_prog: Optional[CopyProgress] = None
        self._copy_refreshing = False
        self._history_refreshing = False
        self._last_log_file = ""

        self._update_card: Optional[ft.Control] = None

        self._setup_page()
        self._build_layout()
        self._reset_task_home()
        self._start_update_check()

    # ---------- 页面基础 ----------
    def _setup_page(self) -> None:
        p = self.page
        p.title = "备份了嘛"
        p.bgcolor = T.BG
        # 注册随包打入的思源黑体（Noto Sans SC 可变字体），让 macOS / Windows
        # 字形与字重完全一致。注册失败（找不到字体文件）时回退系统字体。
        font_path = _bundled_font_path()
        if font_path:
            p.fonts = {T.FONT_FAMILY_NAME: font_path}
            font_family = T.FONT_FAMILY_NAME
        else:
            font_family = "-apple-system" if _IS_MACOS else None
        p.theme_mode = ft.ThemeMode.LIGHT
        p.theme = ft.Theme(
            color_scheme_seed=T.PRIMARY,
            font_family=font_family,
            visual_density=ft.VisualDensity.COMFORTABLE,
        )
        p.window.width = 920
        p.window.height = 600
        p.window.min_width = 720
        p.window.min_height = 480
        # 仅 macOS 隐藏原生标题栏，让侧边栏延伸到窗口顶部、交通灯按钮悬浮其上
        # （macOS 风格无缝侧栏，参考飞书）。Windows/Linux 保留系统标题栏，
        # 以提供右上角最小化 / 最大化 / 关闭三个窗口按钮。
        if _IS_MACOS:
            p.window.title_bar_hidden = True
        # Windows 任务栏/窗口图标：flet 内置客户端默认用 flet logo，需显式指定
        # 随包打入的 .ico，让 Windows 显示「备份了嘛」自定义图标。
        ico = _bundled_icon_path()
        if ico:
            p.window.icon = ico
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
                [ft.WindowDragArea(
                    ft.Container(height=T.HEADER_H)),
                 *self._nav_items],
                spacing=T.SP_1,
            ),
            width=T.SIDEBAR_W,
            bgcolor=T.BG,
            # 右边框贯穿全高（含顶栏），让中间分割线一直延伸到窗口顶部
            border=ft.Border(right=ft.BorderSide(1, T.BORDER)),
        )

        self.content = ft.Container(
            content=None,
            expand=True,
            # 让右侧页面标题文字上沿与左侧导航文字上沿严格对齐：
            # 左侧文字上沿 = HEADER_H + 13(导航容器 40px 内文字垂直居中偏移)
            # 右侧文字上沿 = HEADER_H + padding.top → 取 13
            padding=ft.Padding.only(
                left=T.SP_6, right=T.SP_6, top=13, bottom=T.SP_6),
            bgcolor=T.BG,
        )

        self.page.add(
            ft.Row(
                [sidebar,
                 # 右侧工作区顶部留出等高拖拽条，与侧栏顶栏对齐
                 ft.Column(
                     [ft.WindowDragArea(
                         ft.Container(height=T.HEADER_H, bgcolor=T.BG)),
                      self.content],
                     expand=True,
                     spacing=0,
                 )],
                expand=True,
                spacing=0,
            )
        )

    def _make_nav_item(self, idx: int, icon, label: str) -> ft.Container:
        active = idx == self._nav_index
        fg = T.PRIMARY if active else T.TEXT_PRIMARY
        row_controls = [
            _nav_svg_icon(icon, fg, 18),
            ft.Text(label, size=T.TEXT_14, weight=T.FW_MEDIUM, color=fg),
        ]
        # 「任务」项右侧预留状态槽：备份进行中显示转圈 icon，结束显示红色小标注。
        if idx == 0:
            self._task_status_slot = ft.Container(
                width=14, height=14, alignment=ft.Alignment.CENTER,
                content=None,
            )
            row_controls.append(ft.Container(expand=True))
            row_controls.append(self._task_status_slot)
        item = ft.Container(
            content=ft.Row(row_controls, spacing=T.SP_3, tight=(idx != 0)),
            height=40,
            padding=ft.Padding.only(left=T.SP_4 - 2, right=T.SP_3),
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
                active_now = i == self._nav_index
                hovering = str(e.data).lower() == "true"
                fg = T.PRIMARY_HOVER if hovering else (
                    T.PRIMARY if active_now else T.TEXT_PRIMARY)
                row = c.content
                row.controls[0].color = fg
                row.controls[1].color = fg
                c.bgcolor = (
                    "#C9CDD4" if active_now and hovering
                    else T.PRIMARY_BG if active_now
                    else T.FILL_HOVER if hovering
                    else None
                )
                c.border = ft.Border(left=ft.BorderSide(
                    2, T.PRIMARY_HOVER if active_now and hovering
                    else T.PRIMARY if active_now else "#00000000"))
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

    def _set_task_status(self, status: Optional[str]) -> None:
        """更新「任务」导航项右侧的状态指示器。
        status: "running" 备份进行中（转圈）、"done" 备份结束（红色小标注）、
        None 清除。
        """
        slot = self._task_status_slot
        if slot is None:
            return
        if status == "running":
            slot.content = ft.ProgressRing(
                width=14, height=14, stroke_width=2, color=T.PRIMARY)
        elif status == "done":
            slot.content = ft.Container(
                width=8, height=8, border_radius=4, bgcolor=T.DANGER)
        else:
            slot.content = None
        try:
            slot.update()
        except Exception:
            pass

    def _on_nav_click(self, idx: int) -> None:
        self._nav_index = idx
        if idx != 1:
            self._history_refreshing = False
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
        self._set_task_status(None)
        self._show_home()

    # ---------- 版本更新检测 ----------
    def _start_update_check(self) -> None:
        """启动时在后台线程检测新版本，发现后在右上角弹出更新卡片。"""
        def work() -> None:
            from vaultguard.core.updater import check_for_update
            try:
                info = check_for_update()
            except Exception:  # noqa: BLE001 静默：检测失败不打扰用户
                return
            if info is not None:
                self._run_ui(lambda: self._show_update_card(info))

        threading.Thread(target=work, daemon=True).start()

    def _show_update_card(self, info) -> None:
        """右上角悬浮的更新提示卡片（不抢焦点的轻量浮层）。"""
        self._dismiss_update_card()
        self._update_info = info
        self._update_downloading = False

        # 进度文案：默认隐藏，下载时显示百分比 / 结果。
        self._update_progress_text = _muted_text("", size=T.TEXT_12)
        self._update_progress_text.visible = False

        # 主操作按钮：初始为「下载更新」，点击后触发后台下载。
        self._update_action_btn = _primary_button(
            "下载更新",
            icon=ft.Icons.DOWNLOAD_ROUNDED,
            on_click=self._safe("下载更新",
                                lambda e: self._start_download_update()))

        close_btn = ft.Container(
            content=ft.Icon(ft.Icons.CLOSE_ROUNDED, size=16,
                            color=T.TEXT_TERTIARY),
            width=24, height=24,
            border_radius=T.RADIUS,
            alignment=ft.Alignment.CENTER,
            on_click=self._safe("忽略更新",
                                lambda e: self._dismiss_update_card()),
            ink=False,
        )

        def _close_hover(e: ft.HoverEvent, c=close_btn) -> None:
            try:
                c.bgcolor = T.FILL_HOVER if str(e.data).lower() == "true" else None
                c.update()
            except Exception:
                pass

        close_btn.on_hover = _close_hover

        card = ft.Container(
            width=320,
            bgcolor=T.BG,
            border_radius=T.RADIUS_MD,
            border=ft.Border.all(1, T.BORDER),
            padding=T.SP_4,
            shadow=T.shadow_md(),
            content=ft.Column([
                ft.Row([
                    ft.Row([
                        ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT_ROUNDED,
                                size=18, color=T.PRIMARY),
                        ft.Text("发现新版本", size=T.TEXT_14,
                                weight=T.FW_MEDIUM, color=T.TEXT_TITLE),
                    ], spacing=T.SP_2, tight=True,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    close_btn,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    _mono_text(f"v{__version__}", size=T.TEXT_13,
                               color=T.TEXT_TERTIARY),
                    ft.Icon(ft.Icons.ARROW_FORWARD_ROUNDED, size=14,
                            color=T.TEXT_TERTIARY),
                    _mono_text(f"v{info.version}", size=T.TEXT_13,
                               color=T.PRIMARY),
                ], spacing=T.SP_2, tight=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                _muted_text("有可用的新版本，是否下载更新？",
                            size=T.TEXT_12),
                self._update_progress_text,
                ft.Row([
                    _default_button("忽略",
                                    on_click=self._safe(
                                        "忽略更新",
                                        lambda e: self._dismiss_update_card())),
                    self._update_action_btn,
                ], alignment=ft.MainAxisAlignment.END, spacing=T.SP_2),
            ], spacing=T.SP_3, tight=True),
        )

        # 悬浮在窗口右上角，避让顶部拖拽条（HEADER_H）。
        holder = ft.Container(
            content=card,
            alignment=ft.Alignment.TOP_RIGHT,
            padding=ft.Padding.only(top=T.HEADER_H + T.SP_2, right=T.SP_5),
            expand=True,
        )
        self._update_card = holder
        try:
            self.page.overlay.append(holder)
            self.page.update()
        except Exception:
            self._update_card = None

    def _dismiss_update_card(self) -> None:
        card = self._update_card
        if card is None:
            return
        self._update_card = None
        try:
            self.page.overlay.remove(card)
            self.page.update()
        except Exception:
            pass

    def _start_download_update(self) -> None:
        """点击「下载更新」：后台线程下载安装包到下载目录，卡片内显示进度。"""
        info = getattr(self, "_update_info", None)
        if info is None or self._update_downloading:
            return
        self._update_downloading = True

        # 切换按钮为禁用态文案，显示进度行。
        self._set_update_action("正在下载…", icon=ft.Icons.DOWNLOAD_ROUNDED,
                                disabled=True)
        self._set_update_progress("准备下载…")

        def work() -> None:
            from vaultguard.core import updater
            dest_dir = str(Path.home() / "Downloads")
            last = [0.0]

            def on_progress(done: int, total: int) -> None:
                now = time.monotonic()
                if now - last[0] < 0.1 and done != total:
                    return  # 节流，避免高频 UI 刷新
                last[0] = now
                if total > 0:
                    pct = int(done * 100 / total)
                    txt = f"下载中 {pct}%（{fmt_size(done)} / {fmt_size(total)}）"
                else:
                    txt = f"下载中 {fmt_size(done)}"
                self._run_ui(lambda t=txt: self._set_update_progress(t))

            try:
                path = updater.download_asset(info, dest_dir, on_progress)
            except Exception as ex:  # noqa: BLE001
                self._run_ui(lambda: self._on_download_failed(info))
                self._record_error("下载更新失败", ex)
                return
            self._run_ui(lambda: self._on_download_done(path))

        threading.Thread(target=work, daemon=True).start()

    def _on_download_done(self, path: str) -> None:
        self._update_downloading = False
        self._set_update_progress(f"已下载到：{path}")
        # 下载完成后按钮变为「打开所在文件夹」，方便用户手动安装。
        self._set_update_action(
            "打开所在文件夹", icon=ft.Icons.FOLDER_OPEN_ROUNDED,
            on_click=self._safe("打开下载目录",
                                lambda e, p=path: self._reveal_in_file_manager(p)))
        self._snack("新版本已下载完成")

    def _on_download_failed(self, info) -> None:
        self._update_downloading = False
        self._set_update_progress("下载失败，可前往发布页手动下载")
        # 失败时退回「前往发布页」兜底。
        self._set_update_action(
            "前往发布页", icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
            on_click=self._safe("前往发布页",
                                lambda e, u=info.html_url:
                                    self._open_external_url(u)))

    def _set_update_action(self, text: str, icon=None, on_click=None,
                           disabled: bool = False) -> None:
        """原地替换更新卡片的主操作按钮（重建后局部刷新卡片）。"""
        new_btn = _primary_button(text, icon=icon, on_click=on_click,
                                  disabled=disabled)
        old = getattr(self, "_update_action_btn", None)
        self._update_action_btn = new_btn
        try:
            row = old.parent
            idx = row.controls.index(old)
            row.controls[idx] = new_btn
            row.update()
        except Exception:  # noqa: BLE001
            try:
                self.page.update()
            except Exception:
                pass

    def _set_update_progress(self, text: str) -> None:
        t = getattr(self, "_update_progress_text", None)
        if t is None:
            return
        t.value = text
        t.visible = True
        try:
            t.update()
        except Exception:  # noqa: BLE001
            pass

    def _reveal_in_file_manager(self, path: str) -> bool:
        """在系统文件管理器中定位文件（macOS Finder / Windows 资源管理器）。"""
        import subprocess
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
                return True
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", path])
                return True
            subprocess.Popen(["xdg-open", str(Path(path).parent)])
            return True
        except Exception:  # noqa: BLE001
            return self._open_external_url(str(Path(path).parent))

    def _open_external_url(self, url: str) -> bool:
        """跨平台打开外部链接，返回是否成功。

        打包为 LSUIElement / 无控制台的桌面 app 时 page.launch_url /
        webbrowser 常静默失败，故各平台优先用系统原生方式：
        macOS 用 `open`，Windows 用 os.startfile，Linux 用 xdg-open。
        """
        import subprocess
        if sys.platform == "darwin":
            try:
                subprocess.Popen(["open", url])
                return True
            except Exception:  # noqa: BLE001
                pass
        elif sys.platform.startswith("win"):
            try:
                import os
                os.startfile(url)  # type: ignore[attr-defined]
                return True
            except Exception:  # noqa: BLE001
                pass
            try:
                subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
                return True
            except Exception:  # noqa: BLE001
                pass
        else:
            try:
                subprocess.Popen(["xdg-open", url])
                return True
            except Exception:  # noqa: BLE001
                pass
        try:
            if hasattr(self.page, "launch_url"):
                self.page.launch_url(url)
                return True
        except Exception:  # noqa: BLE001
            pass
        try:
            return bool(webbrowser.open(url))
        except Exception:  # noqa: BLE001
            return False

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
                raise RuntimeError("当前备份了嘛桌面运行时缺少 page.run_task")
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
        if self._open_external_url(mailto):
            self._snack("已打开邮件草稿，请确认后发送")
        else:
            self._snack("打开邮件客户端失败", error=True)

    def _open_overlay(self, control) -> None:
        # Flet 0.85+：弹窗与 SnackBar 都是 DialogControl，统一用 show_dialog。
        # 兼容更早版本：page.open / page.dialog / overlay 依次降级。
        if hasattr(self.page, "show_dialog"):
            self.page.show_dialog(control)
            return
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
        # Flet 0.85+：pop_dialog 弹出当前栈顶弹窗（无参数）。
        if hasattr(self.page, "pop_dialog"):
            try:
                self.page.pop_dialog()
                return
            except Exception:  # noqa: BLE001
                pass
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
            "请输入或选择路径",
            lambda e: setattr(self, "source_path", e.control.value),
            suffix=self._picker_btn(True))
        self.dst_field = self._path_field(
            "目标目录", self.target_path,
            "请输入或选择路径",
            lambda e: setattr(self, "target_path", e.control.value),
            suffix=self._picker_btn(False))

        self._set_task_content(ft.Column([
            self._page_header("你好，今天备份了嘛？"),
            ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
            _card(
                ft.Column([
                    self.src_field,
                    self.dst_field,
                ], spacing=T.SP_5, tight=True),
                ft.Container(height=T.SP_3),
                ft.Row([
                    _primary_button("开始对比",
                                    icon=ft.Icons.COMPARE_ARROWS_ROUNDED,
                                    on_click=self._safe(
                                        "开始对比", lambda e: self._do_compare())),
                ], alignment=ft.MainAxisAlignment.END),
                padding=T.SP_6,
            ),
        ], spacing=T.SP_5, scroll=ft.ScrollMode.AUTO))

    def _path_field(self, label, value, hint, on_change, suffix=None) -> ft.TextField:
        return ft.TextField(
            label=label,
            value=value,
            hint_text=hint,
            on_change=on_change,
            expand=True,
            suffix=suffix,
            border_radius=T.RADIUS,
            border_color=T.BORDER,
            focused_border_color=T.PRIMARY,
            cursor_color=T.PRIMARY,
            text_size=T.TEXT_14,
            content_padding=ft.Padding.symmetric(vertical=8, horizontal=12),
            # 文字/hint 垂直居中（默认即 CENTER=0），与右侧 icon 对齐。
            text_vertical_align=ft.VerticalAlignment.CENTER,
        )

    def _picker_btn(self, is_source: bool) -> ft.Container:
        prompt = "选择源目录" if is_source else "选择目标目录"
        # 配色对齐左侧导航栏：默认灰底（FILL_HOVER #F2F3F5）+ 灰图标；
        # hover 切到导航选中态浅灰（PRIMARY_BG #E5E6EB）+ 黑图标；
        # 按下瞬态再深一档（#C9CDD4，与导航 hover-active 一致）。
        # 不使用 animate / 不切尺寸，避免 suffix 重布局造成的卡顿。
        idle_bg = T.FILL_HOVER          # #F2F3F5
        hover_bg = T.PRIMARY_BG         # #E5E6EB
        active_bg = "#C9CDD4"           # 与左侧导航 hover-active 同色

        icon = _nav_svg_icon(_NAV_SVG_FOLDER, T.TEXT_TERTIARY, 18)
        b = ft.Container(
            content=icon,
            width=28, height=28,
            bgcolor=idle_bg,
            border_radius=T.RADIUS,
            alignment=ft.Alignment.CENTER,
            tooltip="选择源目录" if is_source else "选择目标目录",
            on_click=self._safe(prompt,
                                lambda e, s=is_source: self._pick_dir(s)),
        )

        def _paint(state: str, ctrl=b, ic=icon) -> None:
            # state: "idle" | "hover" | "active"
            try:
                if state == "active":
                    ctrl.bgcolor = active_bg
                    ic.color = T.PRIMARY
                elif state == "hover":
                    ctrl.bgcolor = hover_bg
                    ic.color = T.PRIMARY
                else:
                    ctrl.bgcolor = idle_bg
                    ic.color = T.TEXT_TERTIARY
                ctrl.update()
            except Exception:
                pass

        b.on_hover = lambda e: _paint(
            "hover" if str(e.data).lower() == "true" else "idle")
        # TapDownEvent / TapUpEvent 在部分 Flet 版本中可能未实现，安全降级
        for attr, st in (("on_tap_down", "active"), ("on_tap_up", "hover")):
            try:
                setattr(b, attr, lambda e, s=st: _paint(s))
            except Exception:
                pass
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
        # 文件树展开集合：None 表示首次渲染时默认全部展开
        self._cf_expanded = None
        # 待错位入场动画的目录路径前缀（仅对刚展开的子行生效）
        self._cf_anim_prefix: Optional[str] = None
        # 收集本轮渲染中需要播放入场动画的行，渲染完成后由独立线程错位激活
        self._cf_anim_rows: list = []

        # 顶部统计值随勾选动态更新
        self._cf_stat_new = ft.Text(
            str(diff.new_count), size=T.TEXT_28, weight=T.FW_MEDIUM,
            color=T.SUCCESS, font_family=T.FONT_MONO)
        self._cf_stat_upd = ft.Text(
            str(diff.updated_count), size=T.TEXT_28, weight=T.FW_MEDIUM,
            color=T.WARNING, font_family=T.FONT_MONO)
        self._cf_stat_del = ft.Text(
            str(diff.extra_count), size=T.TEXT_28, weight=T.FW_MEDIUM,
            color=T.DANGER, font_family=T.FONT_MONO)
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
                    stat_cell(self._cf_stat_del, "删除", T.DANGER,
                              ft.Icons.DELETE_OUTLINE_ROUNDED),
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
    def _cf_build_tree(self) -> dict:
        """将待备份清单按目录层级聚合为树结构。

        节点格式：{"dirs": {name: node}, "files": [DiffItem], "path": str}
        """
        root: dict = {"dirs": {}, "files": [], "path": ""}
        for it in self._cf_items:
            parts = Path(it.rel_path).parts
            node = root
            for p in parts[:-1]:
                child = node["dirs"].get(p)
                if child is None:
                    child_path = (node["path"] + "/" + p) if node["path"] else p
                    child = {"dirs": {}, "files": [], "path": child_path}
                    node["dirs"][p] = child
                node = child
            node["files"].append(it)
        return root

    def _cf_dir_items(self, node: dict) -> list:
        """收集目录节点下的所有文件项（含递归）。"""
        result = list(node["files"])
        for sub in node["dirs"].values():
            result.extend(self._cf_dir_items(sub))
        return result

    def _cf_collect_dir_paths(self, node: dict, out: set) -> None:
        for name, sub in node["dirs"].items():
            out.add(sub["path"])
            self._cf_collect_dir_paths(sub, out)

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
        tree = self._cf_build_tree()
        # 默认全部收起，避免一进来就被海量文件淹没
        if self._cf_expanded is None:
            self._cf_expanded = set()
        rows: list = []
        self._cf_anim_rows = []
        self._cf_render_node(tree, depth=0, rows=rows,
                             animate_children=False)
        return ft.ListView(rows, spacing=0, expand=True)

    def _cf_render_node(self, node: dict, depth: int, rows: list,
                        animate_children: bool = False) -> None:
        """递归渲染目录与文件行。

        animate_children=True 表示当前节点处于"刚展开"链路上，其下所有子行
        以隐藏初始态渲染，由调用方在渲染完成后错位激活动画。
        遍历到子目录时，会再次比对 ``self._cf_anim_prefix``，从而支持嵌套
        展开操作各自独立动画。
        """
        # 排序：目录按名称升序；文件按当前排序键
        dir_names = sorted(node["dirs"].keys(), key=lambda s: s.lower())
        for name in dir_names:
            sub = node["dirs"][name]
            row = self._cf_dir_row(name, sub, depth)
            if animate_children:
                self._cf_prepare_anim(row)
            rows.append(row)
            if sub["path"] in self._cf_expanded:
                child_anim = animate_children or (
                    self._cf_anim_prefix is not None
                    and sub["path"] == self._cf_anim_prefix)
                self._cf_render_node(sub, depth + 1, rows,
                                     animate_children=child_anim)
        fn = next(f for k, _l, f, _a in self._CF_SORT_DEFS
                  if k == self._cf_sort_key)
        files_sorted = sorted(node["files"], key=fn,
                              reverse=not self._cf_sort_asc)
        for it in files_sorted:
            row = self._cf_file_row(it, depth)
            if animate_children:
                self._cf_prepare_anim(row)
            rows.append(row)

    def _cf_prepare_anim(self, row: ft.Container) -> None:
        """把一行设置为入场前的隐藏初始态，并登记到待激活列表。"""
        row.opacity = 0
        row.animate_opacity = ft.Animation(T.DUR_BASE, T.EASE)
        self._cf_anim_rows.append(row)

    def _cf_dir_row(self, name: str, node: dict, depth: int) -> ft.Container:
        path = node["path"]
        expanded = path in self._cf_expanded
        all_items = self._cf_dir_items(node)
        sel = sum(1 for it in all_items if id(it) in self._cf_selected)
        total = len(all_items)
        checked = sel == total and total > 0
        partial = 0 < sel < total
        chevron = ft.Icon(
            ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED if expanded
            else ft.Icons.KEYBOARD_ARROW_RIGHT_ROUNDED,
            size=16, color=T.TEXT_TERTIARY)
        mark = self._cf_select_mark(
            checked,
            partial,
            self._safe(
                "选择文件夹",
                lambda e, items=all_items, v=checked:
                    self._cf_toggle_dir(items, not v)))
        folder_icon = ft.Icon(
            ft.Icons.FOLDER_OPEN_ROUNDED if expanded
            else ft.Icons.FOLDER_ROUNDED,
            size=15, color=T.TEXT_TERTIARY)
        total_size = sum(it.size for it in all_items)

        pill = ft.Container(
            content=ft.Row([
                ft.Container(content=chevron, width=18, height=18,
                             alignment=ft.Alignment.CENTER),
                mark,
                folder_icon,
                ft.Text(name, size=T.TEXT_13, expand=True,
                        color=T.TEXT_TITLE, weight=T.FW_MEDIUM,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(f"{sel}/{total}", size=T.TEXT_12,
                        color=T.TEXT_TERTIARY, font_family=T.FONT_MONO),
                ft.Text(fmt_size(total_size), size=T.TEXT_12,
                        color=T.TEXT_TERTIARY, font_family=T.FONT_MONO),
            ], spacing=T.SP_2,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=30,
            padding=ft.Padding.only(left=T.SP_1, right=T.SP_3),
            border_radius=T.RADIUS,
            animate=ft.Animation(T.DUR_FAST, T.EASE),
            on_click=self._safe(
                "展开/收起目录",
                lambda e, p=path: self._cf_toggle_expand(p)),
            ink=False,
        )
        row = self._cf_tree_row(depth, pill)

        def _hover(e: ft.HoverEvent, c=pill) -> None:
            try:
                c.bgcolor = T.FILL_HOVER if e.data == "true" else None
                c.update()
            except Exception:
                pass

        pill.on_hover = _hover
        return row

    def _cf_file_row(self, it, depth: int) -> ft.Container:
        iid = id(it)
        action_val = it.action.value
        if action_val == "new":
            kind = "success"
        elif action_val == "extra":
            kind = "danger"
        else:
            kind = "warning"
        selected = iid in self._cf_selected
        mark = self._cf_select_mark(
            selected,
            False,
            self._safe(
                "选择备份文件",
                lambda e, k=iid, v=selected: self._cf_toggle(k, not v)))
        name = Path(it.rel_path).name
        if kind == "success":
            action_color = T.SUCCESS
        elif kind == "danger":
            action_color = T.DANGER
        else:
            action_color = T.WARNING
        pill = ft.Container(
            content=ft.Row([
                # chevron 占位，对齐目录行。
                ft.Container(width=18, height=18),
                mark,
                ft.Container(
                    content=_nav_svg_icon(_NAV_SVG_DOCUMENT,
                                          T.TEXT_TERTIARY, 14),
                    width=14, height=14,
                    alignment=ft.Alignment.CENTER),
                ft.Text(name, size=T.TEXT_13, expand=True,
                        color=T.TEXT_TITLE,
                        font_family=T.FONT_SANS,
                        weight=T.FW_MEDIUM if selected else T.FW_REGULAR,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Container(width=6, height=6, border_radius=3,
                             bgcolor=action_color),
                ft.Text(fmt_size(it.size), size=T.TEXT_12,
                        color=T.TEXT_TERTIARY, font_family=T.FONT_MONO),
            ], spacing=T.SP_2,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=30,
            padding=ft.Padding.only(left=T.SP_1, right=T.SP_3),
            border_radius=T.RADIUS,
            animate=ft.Animation(T.DUR_FAST, T.EASE),
            on_click=self._safe(
                "选择备份文件",
                lambda e, k=iid, v=selected: self._cf_toggle(k, not v)),
            ink=False,
        )
        row = self._cf_tree_row(depth, pill)

        def _hover(e: ft.HoverEvent, c=pill) -> None:
            try:
                c.bgcolor = T.FILL_HOVER if e.data == "true" else None
                c.update()
            except Exception:
                pass

        pill.on_hover = _hover
        return row

    def _cf_tree_row(self, depth: int, pill: ft.Container) -> ft.Container:
        return ft.Container(
            content=ft.Row([
                ft.Container(width=depth * 20),
                ft.Container(content=pill, expand=True),
            ], spacing=0),
            padding=ft.Padding.symmetric(vertical=1, horizontal=T.SP_3),
        )

    def _cf_select_mark(self, checked: bool, partial: bool,
                        on_click) -> ft.Container:
        content = None
        if checked:
            content = ft.Icon(ft.Icons.CHECK_ROUNDED, size=12, color=T.BG)
        elif partial:
            content = ft.Container(width=8, height=2, bgcolor=T.PRIMARY,
                                   border_radius=1)
        return ft.Container(
            content=content,
            width=14,
            height=14,
            alignment=ft.Alignment.CENTER,
            bgcolor=T.PRIMARY if checked else T.BG,
            border=ft.Border.all(1, T.PRIMARY if (checked or partial)
                                 else T.BORDER),
            border_radius=T.RADIUS_SM,
            on_click=on_click,
            ink=False,
        )

    def _cf_toggle_expand(self, path: str) -> None:
        was_expanded = path in self._cf_expanded
        if was_expanded:
            self._cf_expanded.discard(path)
            self._cf_anim_prefix = None
        else:
            self._cf_expanded.add(path)
            self._cf_anim_prefix = path
        self._cf_list_holder.content = self._cf_build_listview()
        anim_rows = list(self._cf_anim_rows)
        self._cf_anim_rows = []
        self._cf_anim_prefix = None
        # 先以 opacity=0 完成一次首帧布局，再统一切换到 opacity=1
        # 让 Flet 自带的 animate_opacity 过渡完成「淡入」效果，避免每行
        # 单独 update() 带来的卡顿。
        self.page.update()
        if anim_rows and not was_expanded:
            for r in anim_rows:
                try:
                    r.opacity = 1
                except Exception:
                    pass
            try:
                self.page.update()
            except Exception:
                pass

    def _cf_toggle_dir(self, items: list, value) -> None:
        # tristate Checkbox 切换：None / False -> 全选；True -> 全不选
        if value:
            for it in items:
                self._cf_selected.add(id(it))
        else:
            for it in items:
                self._cf_selected.discard(id(it))
        self._cf_list_holder.content = self._cf_build_listview()
        self._cf_sync_meta()

    def _cf_toggle(self, iid: int, value: bool) -> None:
        if value:
            self._cf_selected.add(iid)
        else:
            self._cf_selected.discard(iid)
        # 刷新文件树以同步目录的部分选中态指示
        self._cf_list_holder.content = self._cf_build_listview()
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
        sel_del = sum(1 for it in self._cf_diff.extra_items
                      if id(it) in self._cf_selected)
        # 字节数仅统计实际复制项（删除项不占传输）
        sel_bytes = sum(it.size for it in self._cf_items
                        if id(it) in self._cf_selected
                        and it.action.value != "extra")
        self._cf_stat_new.value = str(sel_new)
        self._cf_stat_upd.value = str(sel_upd)
        self._cf_stat_del.value = str(sel_del)
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
            extra_items=[it for it in diff.extra_items if id(it) in sel],
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
        self._set_task_status("running")
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
        stat_segs = [
            f"{prog.processed_files}/{prog.total_files} 文件",
            f"复制 {prog.copied}",
        ]
        if prog.deleted:
            stat_segs.append(f"删除 {prog.deleted}")
        stat_segs.append(f"失败 {prog.failed}")
        self.lbl_stat.value = " · ".join(stat_segs)
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
        self._set_task_status("done")
        if prog.finished:
            extra = f"，删除 {prog.deleted}" if prog.deleted else ""
            msg = (f"备份完成：复制 {prog.copied}{extra}，失败 {prog.failed}，"
                   f"共 {prog.total_files} 个项。")
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
                *([kv("删除", f"{prog.deleted} 个")] if prog.deleted else []),
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
    def _show_history(self, auto_refresh: bool = True) -> None:
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
        status_col_w = 108

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

        def history_status_bar(t: dict) -> ft.Container:
            total = int(t["total_files"] or 0)
            completed = int(t["copied_files"] or 0)
            failed = int(t["failed_files"] or 0)
            skipped = int(t["skipped_files"] or 0)
            try:
                deleted = int(t["deleted_files"] or 0)
            except (KeyError, IndexError):
                deleted = 0
            if total <= 0:
                total = completed + failed + deleted
            transferring = max(total - completed - failed - deleted, 0)
            deleted_color = (T.DANGER_BG_DEEP if hasattr(T, "DANGER_BG_DEEP")
                             else "#F76560")
            segments = [
                (completed, T.SUCCESS),
                (deleted, deleted_color),
                (transferring, T.PRIMARY),
                (failed, T.DANGER),
            ]
            bars = [
                ft.Container(bgcolor=color, height=6, expand=count)
                for count, color in segments
                if count > 0
            ]
            if not bars:
                bars = [ft.Container(bgcolor=T.BORDER_LIGHT, height=6,
                                     expand=True)]
            # hover 明细：仅展示数量大于 0 的维度
            tip_items = [
                ("复制", completed),
                ("删除", deleted),
                ("跳过", skipped),
                ("传输中", transferring),
                ("失败", failed),
            ]
            tip_lines = [f"{label} {count} 个"
                         for label, count in tip_items if count > 0]
            if tip_lines:
                tooltip = f"共 {total} 个文件\n" + "\n".join(tip_lines)
            else:
                tooltip = "暂无文件变更"
            return ft.Container(
                content=ft.Row(bars, spacing=0, expand=True),
                height=6,
                bgcolor=T.BORDER_LIGHT,
                border_radius=T.RADIUS_SM,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                tooltip=tooltip,
                expand=True,
            )

        def table_row(t: dict, *, last: bool = False) -> ft.Container:
            kind = kind_map.get(t["status"], "running")
            status_label = _task_status_label(t["status"])
            finish_ts = t["end_time"] or None
            finish_text = (
                fmt_relative_time(finish_ts)
                if finish_ts else "进行中"
            )
            detail_btn = ft.Container(
                    content=_nav_svg_icon(_NAV_SVG_DOCUMENT, T.PRIMARY, 18),
                    width=32, height=32,
                    border_radius=T.RADIUS,
                    alignment=ft.Alignment.CENTER,
                    tooltip="查看详情",
                    on_click=self._safe(
                        "查看任务详情",
                        lambda e, tid=t["id"]: self._show_task_detail(tid)))

            def _detail_hover(e: ft.HoverEvent, c=detail_btn) -> None:
                try:
                    c.bgcolor = T.PRIMARY_BG if str(e.data).lower() == "true" else None
                    c.update()
                except Exception:
                    pass

            detail_btn.on_hover = _detail_hover
            return ft.Container(
                content=ft.Row([
                    cell(_mono_text(f"#{t['id']}", size=T.TEXT_13,
                                    color=T.TEXT_TITLE), width=70),
                    cell(_badge(status_label, kind), width=status_col_w,
                         align=ft.Alignment.CENTER),
                    cell(history_status_bar(t), expand=3),
                    cell(ft.Text(finish_text, size=T.TEXT_13,
                                 color=T.TEXT_PRIMARY,
                                 overflow=ft.TextOverflow.ELLIPSIS),
                         expand=2),
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
                head("任务", width=status_col_w),
                head("状态", expand=3),
                head("结束时间", expand=2),
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

        has_active_task = any(
            t["status"] in ("pending", "running", "paused") for t in tasks)
        if not has_active_task:
            self._history_refreshing = False
        elif auto_refresh and not self._history_refreshing:
            self._history_refreshing = True

            async def refresh_history():
                while self._history_refreshing and self._nav_index == 1:
                    await asyncio.sleep(1)
                    if self._nav_index != 1:
                        break
                    self._show_history(auto_refresh=False)

            self._start_refresher(refresh_history, "历史记录刷新")

    def _show_task_detail(self, task_id: int) -> None:
        try:
            logs = self.svc.get_file_logs(task_id)
            task = self.svc.db.get_task(task_id)
        except Exception as ex:  # noqa: BLE001
            self._handle_error("加载任务详情", ex)
            return

        groups = {"copy": [], "delete": [], "fail": []}
        for lg in logs:
            act = lg["action"]
            if act in groups:
                groups[act].append(dict(lg))

        group_meta = [
            ("copy", "复制", T.SUCCESS,
             ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED),
            ("delete", "删除", T.DANGER,
             ft.Icons.DELETE_OUTLINE_ROUNDED),
            ("fail", "失败", T.WARNING,
             ft.Icons.ERROR_OUTLINE_ROUNDED),
        ]

        # 每组维护独立的展开目录集合，初始全部收起。
        expanded_state: dict[str, set[str]] = {k: set() for k, *_ in group_meta}

        def build_tree(items: list[dict]) -> dict:
            root: dict = {"dirs": {}, "files": [], "path": ""}
            for it in items:
                parts = Path(it["file_path"]).parts
                node = root
                for p in parts[:-1]:
                    child = node["dirs"].get(p)
                    if child is None:
                        child_path = (node["path"] + "/" + p) if node["path"] else p
                        child = {"dirs": {}, "files": [], "path": child_path}
                        node["dirs"][p] = child
                    node = child
                node["files"].append(it)
            return root

        list_holder = ft.Container(content=None, expand=True)
        # 持久化 ListView：展开/收起时仅替换其 controls 并局部刷新，
        # 避免重建控件树导致滚动位置被重置（"点一下就弹走"）。
        tree_list = ft.ListView(spacing=0, padding=0, expand=True)
        list_holder.content = tree_list

        def render_node(node: dict, depth: int, rows: list,
                        expanded: set[str], color: str) -> None:
            for name in sorted(node["dirs"].keys(), key=lambda s: s.lower()):
                sub = node["dirs"][name]
                is_open = sub["path"] in expanded
                file_count = _count_files(sub)
                rows.append(_make_dir_row(name, sub["path"], depth, is_open,
                                          file_count, expanded, color))
                if is_open:
                    render_node(sub, depth + 1, rows, expanded, color)
            for it in sorted(node["files"], key=lambda x: x["file_path"]):
                rows.append(_make_file_row(it, depth, color))

        def _count_files(node: dict) -> int:
            n = len(node["files"])
            for sub in node["dirs"].values():
                n += _count_files(sub)
            return n

        def _make_dir_row(name: str, path: str, depth: int,
                          is_open: bool, file_count: int,
                          expanded: set[str], color: str) -> ft.Container:
            chevron = ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED if is_open
                else ft.Icons.KEYBOARD_ARROW_RIGHT_ROUNDED,
                size=16, color=T.TEXT_TERTIARY)
            folder_icon = ft.Icon(
                ft.Icons.FOLDER_OPEN_ROUNDED if is_open
                else ft.Icons.FOLDER_ROUNDED,
                size=15, color=T.TEXT_TERTIARY)
            pill = ft.Container(
                content=ft.Row([
                    ft.Container(width=18, height=18,
                                 content=chevron,
                                 alignment=ft.Alignment.CENTER),
                    folder_icon,
                    ft.Text(name, size=T.TEXT_13, expand=True,
                            color=T.TEXT_TITLE, weight=T.FW_MEDIUM,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(f"{file_count} 项", size=T.TEXT_12,
                            color=T.TEXT_TERTIARY, font_family=T.FONT_MONO),
                ], spacing=T.SP_2,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                height=28,
                padding=ft.Padding.only(left=T.SP_1, right=T.SP_3),
                border_radius=T.RADIUS,
                animate=ft.Animation(T.DUR_FAST, T.EASE),
                on_click=self._safe(
                    "展开/收起目录",
                    lambda e, p=path, ex=expanded:
                        _toggle_dir(p, ex)),
                ink=False,
            )

            def _hover(e: ft.HoverEvent, c=pill) -> None:
                try:
                    c.bgcolor = T.FILL_HOVER if e.data == "true" else None
                    c.update()
                except Exception:
                    pass

            pill.on_hover = _hover
            return ft.Container(
                content=ft.Row([
                    ft.Container(width=depth * 18),
                    ft.Container(content=pill, expand=True),
                ], spacing=0),
                padding=ft.Padding.symmetric(vertical=1, horizontal=T.SP_2),
            )

        def _make_file_row(it: dict, depth: int, color: str) -> ft.Container:
            name = Path(it["file_path"]).name
            size_text = fmt_size(it["size"]) if it["size"] else "--"
            reason_text = (it["reason"] or "").replace("error_", "").replace(
                "ok_", "")
            reason_widget = (
                _muted_text(reason_text, size=T.TEXT_12)
                if reason_text and reason_text not in ("new", "updated")
                else _muted_text(size_text, size=T.TEXT_12)
            )
            pill = ft.Container(
                content=ft.Row([
                    ft.Container(width=18, height=18),
                    ft.Container(width=6, height=6, border_radius=3,
                                 bgcolor=color),
                    ft.Container(
                        content=_nav_svg_icon(_NAV_SVG_DOCUMENT,
                                              T.TEXT_TERTIARY, 14),
                        width=14, height=14,
                        alignment=ft.Alignment.CENTER),
                    ft.Text(name, size=T.TEXT_13, expand=True,
                            color=T.TEXT_PRIMARY,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            tooltip=it["file_path"]),
                    reason_widget,
                ], spacing=T.SP_2,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                height=28,
                padding=ft.Padding.only(left=T.SP_1, right=T.SP_3),
                border_radius=T.RADIUS,
                animate=ft.Animation(T.DUR_FAST, T.EASE),
                ink=False,
            )

            def _hover(e: ft.HoverEvent, c=pill) -> None:
                try:
                    c.bgcolor = T.FILL_HOVER if e.data == "true" else None
                    c.update()
                except Exception:
                    pass

            pill.on_hover = _hover
            return ft.Container(
                content=ft.Row([
                    ft.Container(width=depth * 18),
                    ft.Container(content=pill, expand=True),
                ], spacing=0),
                padding=ft.Padding.symmetric(vertical=1, horizontal=T.SP_2),
            )

        # 每组的标题行（点击切换该组所有顶层目录）
        section_state = {"copy": True, "delete": True, "fail": True}

        def _toggle_section(key: str) -> None:
            section_state[key] = not section_state[key]
            _rerender()

        def _toggle_dir(path: str, expanded: set[str]) -> None:
            if path in expanded:
                expanded.discard(path)
            else:
                expanded.add(path)
            _rerender()

        def _expand_all(key: str) -> None:
            tree = build_tree(groups[key])
            paths: set[str] = set()
            _collect_dirs(tree, paths)
            expanded_state[key] = paths
            section_state[key] = True
            _rerender()

        def _collapse_all(key: str) -> None:
            expanded_state[key] = set()
            _rerender()

        def _collect_dirs(node: dict, out: set[str]) -> None:
            for sub in node["dirs"].values():
                if sub["path"]:
                    out.add(sub["path"])
                _collect_dirs(sub, out)

        def _section_header(key: str, label: str, color: str, icon) -> ft.Container:
            count = len(groups[key])
            opened = section_state[key]
            chevron = ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED if opened
                else ft.Icons.KEYBOARD_ARROW_RIGHT_ROUNDED,
                size=16, color=T.TEXT_TERTIARY)
            actions = []
            if count > 0:
                actions = [
                    ft.Container(
                        content=ft.Text("展开全部", size=T.TEXT_12,
                                        color=T.TEXT_TERTIARY),
                        on_click=self._safe(
                            f"展开{label}全部目录",
                            lambda e, k=key: _expand_all(k)),
                        padding=ft.Padding.symmetric(vertical=2, horizontal=6),
                        border_radius=T.RADIUS_SM,
                    ),
                    ft.Container(
                        content=ft.Text("全部收起", size=T.TEXT_12,
                                        color=T.TEXT_TERTIARY),
                        on_click=self._safe(
                            f"收起{label}全部目录",
                            lambda e, k=key: _collapse_all(k)),
                        padding=ft.Padding.symmetric(vertical=2, horizontal=6),
                        border_radius=T.RADIUS_SM,
                    ),
                ]
            return ft.Container(
                content=ft.Row([
                    ft.Container(content=chevron, width=18,
                                 alignment=ft.Alignment.CENTER),
                    ft.Icon(icon, size=14, color=color),
                    ft.Text(label, size=T.TEXT_13, weight=T.FW_MEDIUM,
                            color=T.TEXT_TITLE),
                    ft.Container(
                        content=ft.Text(str(count), size=T.TEXT_12,
                                        color=color,
                                        font_family=T.FONT_MONO,
                                        weight=T.FW_MEDIUM),
                        bgcolor=({"copy": T.SUCCESS_BG,
                                  "delete": T.DANGER_BG,
                                  "fail": T.WARNING_BG}.get(key, T.FILL)),
                        padding=ft.Padding.symmetric(vertical=1, horizontal=6),
                        border_radius=T.RADIUS_SM,
                    ),
                    ft.Container(expand=True),
                    *actions,
                ], spacing=T.SP_2,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                height=32,
                padding=ft.Padding.symmetric(horizontal=T.SP_3),
                bgcolor=T.FILL,
                border=ft.Border(bottom=ft.BorderSide(1, T.BORDER_LIGHT)),
                on_click=self._safe(
                    f"切换{label}分组",
                    lambda e, k=key: _toggle_section(k)),
                ink=False,
            )

        def _rerender(first: bool = False) -> None:
            rows: list = []
            for key, label, color, icon in group_meta:
                rows.append(_section_header(key, label, color, icon))
                if not section_state[key]:
                    continue
                if not groups[key]:
                    rows.append(ft.Container(
                        content=_muted_text(f"无{label}文件",
                                            size=T.TEXT_12),
                        padding=ft.Padding.symmetric(
                            vertical=T.SP_2, horizontal=T.SP_5),
                    ))
                    continue
                tree = build_tree(groups[key])
                render_node(tree, depth=0, rows=rows,
                            expanded=expanded_state[key], color=color)
                rows.append(ft.Container(height=T.SP_1))
            # 仅替换持久化 ListView 的 controls，保留滚动位置；
            # 首次渲染走整页刷新，后续交互只局部 update 该列表。
            tree_list.controls = rows
            if first:
                return
            try:
                tree_list.update()
            except Exception:
                try:
                    self.page.update()
                except Exception:
                    pass

        _rerender(first=True)

        # 头部摘要（复制 / 删除 / 失败 数量）
        copied_n = len(groups["copy"])
        deleted_n = len(groups["delete"])
        failed_n = len(groups["fail"])
        summary = ft.Row([
            _detail_summary_chip(ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED,
                                 T.SUCCESS, "复制", copied_n),
            _detail_summary_chip(ft.Icons.DELETE_OUTLINE_ROUNDED,
                                 T.DANGER, "删除", deleted_n),
            _detail_summary_chip(ft.Icons.ERROR_OUTLINE_ROUNDED,
                                 T.WARNING, "失败", failed_n),
        ], spacing=T.SP_2,
           vertical_alignment=ft.CrossAxisAlignment.CENTER)

        body = ft.Container(
            content=ft.Column([
                summary,
                ft.Container(
                    content=list_holder,
                    border=ft.Border.all(1, T.BORDER),
                    border_radius=T.RADIUS_MD,
                    expand=True,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
            ], spacing=T.SP_3, expand=True),
            width=720, height=480,
        )

        dlg = ft.AlertDialog(
            title=ft.Text(
                f"任务 #{task_id} 详情"
                + (f" · {_task_status_label(task['status'])}" if task else ""),
                weight=T.FW_MEDIUM, size=T.TEXT_16, color=T.TEXT_TITLE),
            content=body,
            shape=ft.RoundedRectangleBorder(radius=T.RADIUS_MD),
            actions=[_default_button(
                "关闭", on_click=self._safe(
                    "关闭任务详情", lambda e: self._close_overlay(dlg)))],
        )
        self._open_overlay(dlg)

    # ========== 设置页 ==========
    def _show_settings(self) -> None:
        s = self.svc.settings

        def _tf(value, **kw) -> ft.TextField:
            return ft.TextField(
                value=value,
                border_radius=T.RADIUS,
                border_color=T.BORDER,
                focused_border_color=T.PRIMARY,
                cursor_color=T.PRIMARY,
                text_size=T.TEXT_14,
                content_padding=ft.Padding.symmetric(vertical=8, horizontal=12),
                **kw,
            )

        def _setting_title(title: str, desc: str) -> ft.Column:
            return ft.Column([
                ft.Text(title, size=T.TEXT_14, weight=T.FW_MEDIUM,
                        color=T.TEXT_TITLE, font_family=T.FONT_SANS),
                _muted_text(desc, size=T.TEXT_12),
            ], spacing=2, tight=True, expand=True)

        def _divider() -> ft.Container:
            return ft.Container(height=1, bgcolor=T.BORDER_LIGHT)

        def _section_label(title: str) -> ft.Container:
            return ft.Container(
                content=ft.Text(
                    title, size=T.TEXT_14, weight=T.FW_SEMIBOLD,
                    color=T.TEXT_TITLE, font_family=T.FONT_SANS),
                padding=ft.Padding.only(left=16, right=16, top=18, bottom=10),
                bgcolor=T.BG,
            )

        def _setting_row(title: str, desc: str, control,
                         danger: bool = False) -> ft.Container:
            return ft.Container(
                content=ft.Row([
                    _setting_title(title, desc),
                    control,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=T.SP_4),
                padding=ft.Padding.symmetric(vertical=14, horizontal=16),
                bgcolor=T.DANGER_BG if danger else T.BG,
            )

        def _field_row(title: str, desc: str, field) -> ft.Container:
            return ft.Container(
                content=ft.Row([
                    _setting_title(title, desc),
                    field,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=T.SP_4),
                padding=ft.Padding.symmetric(vertical=14, horizontal=16),
                bgcolor=T.BG,
            )

        def _textarea_row(title: str, desc: str, field) -> ft.Container:
            return ft.Container(
                content=ft.Column([
                    _setting_title(title, desc),
                    field,
                ], spacing=T.SP_3, tight=True),
                padding=ft.Padding.symmetric(vertical=14, horizontal=16),
                bgcolor=T.BG,
            )

        def _settings_list(*controls) -> ft.Container:
            return ft.Container(
                bgcolor=T.BG,
                expand=True,
                content=ft.Column(
                    list(controls), spacing=0,
                    scroll=ft.ScrollMode.AUTO, expand=True),
            )

        self.f_tolerance = _tf(
            str(s.mtime_tolerance),
            width=160, dense=True,
            keyboard_type=ft.KeyboardType.NUMBER)
        self.f_compare_size = ft.Switch(
            value=s.compare_size, active_color=T.PRIMARY)
        self.f_verify_hash = ft.Switch(
            value=s.verify_hash, active_color=T.PRIMARY)
        self.f_delete_sync = ft.Switch(
            value=s.delete_sync, active_color=T.DANGER)
        self.f_use_recycle = ft.Switch(
            value=s.use_recycle, active_color=T.PRIMARY)
        self.f_exclude = _tf(
            "\n".join(s.exclude_patterns),
            multiline=True, min_lines=3, max_lines=8)
        self.f_retry = _tf(
            str(s.retry_times),
            width=160, dense=True,
            keyboard_type=ft.KeyboardType.NUMBER)

        from vaultguard.core.config import default_app_data_dir
        is_default_dir = (
            Path(self.svc.data_dir).resolve()
            == default_app_data_dir().expanduser().resolve()
        )
        data_dir_path_text = ft.Text(
            f"数据/日志/配置位置：{self.svc.data_dir}",
            size=T.TEXT_12,
            color=T.TEXT_TERTIARY,
            font_family=T.FONT_MONO,
            expand=True,
            overflow=ft.TextOverflow.ELLIPSIS)
        change_dir_btn = _default_button(
            "更改位置", icon=ft.Icons.DRIVE_FILE_MOVE_OUTLINED,
            on_click=self._safe(
                "更改数据目录", lambda e: self._pick_data_dir()))
        reset_dir_btn = _default_button(
            "恢复默认", icon=ft.Icons.RESTORE_ROUNDED,
            on_click=self._safe(
                "恢复默认数据目录", lambda e: self._reset_data_dir()),
            disabled=is_default_dir,
            tooltip=("当前已是默认位置" if is_default_dir else None))
        data_dir_row = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.FOLDER_SHARED_OUTLINED,
                            color=T.TEXT_TERTIARY, size=17),
                    data_dir_path_text,
                ], spacing=T.SP_2,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([change_dir_btn, reset_dir_btn],
                       spacing=T.SP_2,
                       alignment=ft.MainAxisAlignment.END),
            ], spacing=T.SP_3, tight=True),
            padding=ft.Padding.symmetric(vertical=9, horizontal=12),
            border_radius=T.RADIUS,
            bgcolor=T.FILL,
        )

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

        settings_list = _settings_list(
            _section_label("对比策略"),
            _field_row(
                "mtime 容差",
                "允许源目录与目标目录的文件时间存在轻微误差，单位为秒。",
                self.f_tolerance),
            _divider(),
            _setting_row(
                "检测文件容量变化",
                "容量变化会被视为需要同步，适合增量备份默认开启。",
                self.f_compare_size),
            _section_label("文件安全"),
            _setting_row(
                "Hash 校验",
                "复制完成后校验文件内容，速度更慢但可靠性更高。",
                self.f_verify_hash),
            _divider(),
            _field_row(
                "失败重试次数",
                "单个文件复制失败后的自动重试次数。",
                self.f_retry),
            _section_label("删除策略"),
            _setting_row(
                "删除同步",
                "目标目录中多余文件会随源目录删除，开启前请确认备份策略。",
                self.f_delete_sync,
                danger=True),
            _divider(),
            _setting_row(
                "移入回收区",
                "删除同步时优先移入系统回收区，降低误删风险。",
                self.f_use_recycle),
            _section_label("排除规则"),
            _textarea_row(
                "忽略文件与目录",
                "命中的文件或目录不会参与对比与备份。",
                self.f_exclude),
            _section_label("错误反馈"),
            ft.Container(
                content=data_dir_row,
                padding=ft.Padding.only(left=16, right=16, top=14),
                bgcolor=T.BG,
            ),
            ft.Container(
                content=ft.Column([
                    ft.Text(f"异常报告目录：{self.error_reporter.report_dir}",
                            size=T.TEXT_12,
                            color=T.TEXT_TERTIARY,
                            font_family=T.FONT_MONO,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Row([report_btn], alignment=ft.MainAxisAlignment.END),
                ], spacing=T.SP_3, tight=True),
                padding=ft.Padding.symmetric(vertical=14, horizontal=16),
                bgcolor=T.BG,
            ),
        )

        # 设置面板自适应：用 Row 强制让面板撑满 content 区域可用宽度，
        # 不再写死 736px，从而在窗口任意宽度下都不会出现右侧大片空白。
        # 滚动条收在面板边框内部（参考历史记录页），底部“保存设置”按钮固定，
        # 避免滚动条覆盖到按钮。
        self._set_content(ft.Column([
            self._page_header("设置"),
            ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
            ft.Row([
                ft.Container(content=settings_list, expand=True),
            ], spacing=0, expand=True),
            ft.Row([save_btn], alignment=ft.MainAxisAlignment.END),
        ], spacing=T.SP_4, expand=True))

    # ========== 数据目录切换 ==========
    def _pick_data_dir(self) -> None:
        """弹出原生面板让用户选择新的数据目录，确认后迁移并重启。"""
        if self._running:
            self._snack("备份进行中，无法切换数据目录", error=True)
            return

        def work() -> None:
            from .dirpicker import pick_directory
            try:
                path = pick_directory("选择备份了嘛数据目录")
            except Exception as e:  # noqa: BLE001
                self._handle_error("选择数据目录", e)
                return
            if not path:
                return
            self._run_ui(lambda: self._show_switch_dialog(path))

        threading.Thread(target=work, daemon=True).start()

    def _reset_data_dir(self) -> None:
        if self._running:
            self._snack("备份进行中，无法切换数据目录", error=True)
            return
        from vaultguard.core.config import default_app_data_dir
        target = str(default_app_data_dir())
        if Path(target).resolve() == Path(self.svc.data_dir).resolve():
            self._snack("当前已是默认数据目录")
            return
        self._show_switch_dialog(target)

    def _show_switch_dialog(self, new_path: str) -> None:
        """单一对话框：确认 → 迁移中 → 完成并重启，三态原地切换。

        采用单 Dialog 多状态，避免 Flet 对快速 close/open 两个 Dialog
        时第二个被吞掉的问题（这是用户「点了没反应」的真正成因）。
        """
        new_resolved = Path(new_path).expanduser().resolve()
        cur_resolved = Path(self.svc.data_dir).resolve()
        if new_resolved == cur_resolved:
            self._snack("所选目录与当前数据目录相同")
            return

        # 弹窗主体（用 Container 包住 Column，状态切换时直接替换 Column 内容）
        body_col = ft.Column(spacing=T.SP_3, tight=True)
        body = ft.Container(width=520, content=body_col)

        confirm_btn_holder: list = [None]
        cancel_btn_holder: list = [None]

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("切换数据目录",
                          weight=T.FW_MEDIUM, size=T.TEXT_16,
                          color=T.TEXT_TITLE),
            content=body,
            shape=ft.RoundedRectangleBorder(radius=T.RADIUS_MD),
            actions=[],
        )

        def _render_confirm() -> None:
            body_col.controls = [
                ft.Text("确认要把数据目录切换到下列位置吗？",
                        size=T.TEXT_14, color=T.TEXT_PRIMARY),
                ft.Container(
                    content=ft.Column([
                        ft.Text(f"原位置：{cur_resolved}",
                                size=T.TEXT_12, color=T.TEXT_TERTIARY,
                                font_family=T.FONT_MONO, selectable=True),
                        ft.Text(f"新位置：{new_resolved}",
                                size=T.TEXT_12, color=T.TEXT_PRIMARY,
                                font_family=T.FONT_MONO, selectable=True),
                    ], spacing=T.SP_2, tight=True),
                    padding=ft.Padding.symmetric(vertical=8, horizontal=12),
                    bgcolor=T.FILL, border_radius=T.RADIUS,
                ),
                ft.Text("将把 config.json、vaultguard.db、logs/、error_reports/ "
                        "整体迁移到新位置，原位置上述内容会被清除。",
                        size=T.TEXT_12, color=T.TEXT_TERTIARY),
                ft.Text("迁移完成后会自动重启备份了嘛以保证句柄干净。",
                        size=T.TEXT_12, color=T.WARNING),
            ]
            cancel_btn = _default_button(
                "取消",
                on_click=self._safe(
                    "取消切换数据目录",
                    lambda e: self._close_overlay(dlg)))
            confirm_btn = _primary_button(
                "迁移并重启", icon=ft.Icons.DRIVE_FILE_MOVE_OUTLINED,
                on_click=self._safe(
                    "开始迁移",
                    lambda e: _start_migrate()))
            cancel_btn_holder[0] = cancel_btn
            confirm_btn_holder[0] = confirm_btn
            dlg.actions = [cancel_btn, confirm_btn]
            try:
                self.page.update()
            except Exception:
                pass

        def _render_progress() -> None:
            body_col.controls = [
                ft.Row([
                    ft.ProgressRing(width=18, height=18, stroke_width=2,
                                    color=T.PRIMARY),
                    ft.Text("正在迁移数据，请勿关闭窗口…",
                            size=T.TEXT_14, color=T.TEXT_PRIMARY),
                ], spacing=T.SP_3,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(
                    content=ft.Text(f"目标位置：{new_resolved}",
                                    size=T.TEXT_12, color=T.TEXT_TERTIARY,
                                    font_family=T.FONT_MONO, selectable=True),
                    padding=ft.Padding.symmetric(vertical=8, horizontal=12),
                    bgcolor=T.FILL, border_radius=T.RADIUS,
                ),
            ]
            dlg.actions = []
            try:
                self.page.update()
            except Exception:
                pass

        def _render_done() -> None:
            body_col.controls = [
                ft.Row([
                    ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED,
                            color=T.SUCCESS, size=20),
                    ft.Text("迁移完成，备份了嘛即将重启以使新位置生效。",
                            size=T.TEXT_14, color=T.TEXT_PRIMARY),
                ], spacing=T.SP_3,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(
                    content=ft.Text(f"新位置：{new_resolved}",
                                    size=T.TEXT_12, color=T.TEXT_PRIMARY,
                                    font_family=T.FONT_MONO, selectable=True),
                    padding=ft.Padding.symmetric(vertical=8, horizontal=12),
                    bgcolor=T.FILL, border_radius=T.RADIUS,
                ),
            ]
            dlg.actions = [_primary_button(
                "立即重启", icon=ft.Icons.RESTART_ALT_ROUNDED,
                on_click=self._safe("立即重启",
                                    lambda e: self._restart_app()))]
            try:
                self.page.update()
            except Exception:
                pass

        def _render_failed(msg: str) -> None:
            body_col.controls = [
                ft.Row([
                    ft.Icon(ft.Icons.ERROR_ROUNDED, color=T.DANGER, size=20),
                    ft.Text("迁移失败，原数据保持不变。",
                            size=T.TEXT_14, color=T.TEXT_PRIMARY),
                ], spacing=T.SP_3,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Text(msg, size=T.TEXT_12, color=T.DANGER,
                        selectable=True),
            ]
            dlg.actions = [_default_button(
                "关闭",
                on_click=self._safe("关闭迁移失败弹窗",
                                    lambda e: self._close_overlay(dlg)))]
            try:
                self.page.update()
            except Exception:
                pass

        def _start_migrate() -> None:
            _render_progress()
            threading.Thread(target=_do_migrate, daemon=True).start()

        def _do_migrate() -> None:
            from vaultguard.core.config import set_custom_data_dir
            try:
                try:
                    self.svc.close()
                except Exception:
                    pass
                set_custom_data_dir(Path(new_resolved), migrate=True)
            except Exception as ex:  # noqa: BLE001
                self._record_error("迁移数据目录", ex)
                self._run_ui(lambda: _render_failed(
                    f"{type(ex).__name__}: {ex}"))
                return
            self._run_ui(_render_done)

        _render_confirm()
        self._open_overlay(dlg)

    def _restart_app(self) -> None:
        """关闭当前窗口并拉起新的 VaultGuard 进程。

        采用 detach shell（`nohup sh -c '...' &`）而非直接 Popen，
        确保即使本进程立刻 _exit，子命令也由 launchd 接管不会被中断。
        """
        import os
        import shlex
        import subprocess
        import sys

        try:
            if getattr(sys, "frozen", False) and sys.platform == "darwin":
                exe = Path(sys.executable).resolve()
                app_bundle = exe.parents[2] if len(exe.parents) >= 3 else None
                if app_bundle and app_bundle.suffix == ".app":
                    cmd = (f"sleep 0.5 && open -n "
                           f"{shlex.quote(str(app_bundle))}")
                else:
                    cmd = f"sleep 0.5 && {shlex.quote(str(exe))}"
                subprocess.Popen(["/bin/sh", "-c", cmd],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL,
                                 start_new_session=True)
            elif getattr(sys, "frozen", False):
                subprocess.Popen([sys.executable],
                                 start_new_session=True)
            else:
                main_py = Path(__file__).resolve().parents[2] / "main.py"
                subprocess.Popen([sys.executable, str(main_py)],
                                 start_new_session=True)
        except Exception as ex:  # noqa: BLE001
            self._handle_error("拉起新进程", ex)
            return

        try:
            self.page.window.close()
        except Exception:
            pass
        os._exit(0)

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
