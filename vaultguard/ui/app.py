"""VaultGuard Flet 图形界面（模块 5 + 6）。

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

import threading
import time
from pathlib import Path
from typing import Optional

import flet as ft

from vaultguard.core.models import CompareProgress, CopyProgress, DiffResult
from vaultguard.core.service import BackupService
from . import tokens as T
from .helpers import fmt_eta, fmt_size, fmt_time


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
        btn.bgcolor = T.PRIMARY_HOVER if e.data == "true" else T.PRIMARY
        btn.update()

    if not disabled:
        btn.on_hover = _hover
    return btn


def _default_button(text: str, icon=None, on_click=None,
                    danger: bool = False) -> ft.Container:
    """次按钮：描边（规范 §5.1 .vg-btn--default）。

    hover 仅变边框/文字色为主色；danger 变体用危险色描边。
    """
    base_color = T.DANGER if danger else T.TEXT_PRIMARY
    base_border = T.DANGER if danger else T.BORDER
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
        on_click=on_click,
        ink=False,
    )

    def _hover(e: ft.HoverEvent) -> None:
        on = e.data == "true"
        col = hover_color if on else base_color
        bdr = hover_color if on else base_border
        btn.border = ft.Border.all(1, bdr)
        label.color = col
        if icon_ctrl is not None:
            icon_ctrl.color = col
        btn.update()

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
        self.executor = None
        self.current_diff: Optional[DiffResult] = None
        self.current_task_id: Optional[int] = None
        self.source_path = self.svc.settings.last_source
        self.target_path = self.svc.settings.last_target
        self._running = False
        self._nav_index = 0
        self._nav_items: list[ft.Container] = []
        self._compare_started_at = 0.0

        self._setup_page()
        self._build_layout()
        self._show_home()

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
            (ft.Icons.HOME_OUTLINED, "主页"),
            (ft.Icons.HISTORY_OUTLINED, "历史"),
            (ft.Icons.SETTINGS_OUTLINED, "设置"),
        ]
        self._nav_items = []
        for idx, (icon, label) in enumerate(nav_defs):
            self._nav_items.append(self._make_nav_item(idx, icon, label))

        brand = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.SHIELD_OUTLINED, color=T.PRIMARY, size=20),
                ft.Text("VaultGuard", size=T.TEXT_16, weight=T.FW_MEDIUM,
                        color=T.TEXT_TITLE),
            ], spacing=T.SP_2, tight=True),
            height=T.HEADER_H,
            padding=ft.Padding.symmetric(vertical=0, horizontal=T.SP_5),
            alignment=ft.Alignment.CENTER_LEFT,
        )

        sidebar = ft.Container(
            content=ft.Column(
                [brand,
                 ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
                 ft.Container(height=T.SP_2),
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
                ft.Icon(icon, color=fg, size=18),
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
            on_click=lambda e, i=idx: self._on_nav_click(i),
        )
        item.data = (idx, icon, label)

        def _hover(e: ft.HoverEvent, c=item) -> None:
            i = c.data[0]
            if i == self._nav_index:
                return
            c.bgcolor = T.FILL if e.data == "true" else None
            c.update()

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
            self._show_home()
        elif idx == 1:
            self._show_history()
        elif idx == 2:
            self._show_settings()

    def _set_content(self, control) -> None:
        self.content.content = control
        self.page.update()

    def _snack(self, msg: str, error: bool = False) -> None:
        self.page.open(
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
        self.src_field = self._path_field(
            "源目录", self.source_path,
            "路径",
            lambda e: setattr(self, "source_path", e.control.value))
        self.dst_field = self._path_field(
            "目标目录", self.target_path,
            "路径",
            lambda e: setattr(self, "target_path", e.control.value))

        self._set_content(ft.Column([
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
                                    on_click=lambda e: self._do_compare()),
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
        b = ft.Container(
            content=ft.Icon(ft.Icons.FOLDER_OPEN_OUTLINED,
                            color=T.TEXT_PRIMARY, size=18),
            width=32, height=32,
            bgcolor=T.BG,
            border=ft.Border.all(1, T.BORDER),
            border_radius=T.RADIUS,
            alignment=ft.Alignment.CENTER,
            tooltip="选择源目录" if is_source else "选择目标目录",
            on_click=lambda e, s=is_source: self._pick_dir(s),
            animate=ft.Animation(T.DUR_FAST, T.EASE),
        )

        def _hover(e: ft.HoverEvent, ctrl=b) -> None:
            on = e.data == "true"
            ctrl.border = ft.Border.all(1, T.PRIMARY if on else T.BORDER)
            ctrl.content.color = T.PRIMARY if on else T.TEXT_PRIMARY
            ctrl.update()

        b.on_hover = _hover
        return b

    def _pick_dir(self, is_source: bool) -> None:
        # 通过 VaultGuard 自身的独立子进程运行原生 NSOpenPanel：既避免在 Flet
        # 工作线程里直接碰 AppKit 导致卡顿/闪退，又让发起面板请求的进程 main
        # bundle 是已声明中文本地化的 VaultGuard.app，使系统面板显示中文。
        prompt = "选择源目录" if is_source else "选择目标目录"

        def work() -> None:
            from .dirpicker import pick_directory
            try:
                path = pick_directory(prompt)
            except Exception as e:  # noqa: BLE001
                self._snack(f"选择目录失败：{e}", error=True)
                return
            if not path:
                return
            if is_source:
                self.source_path = path
                self.src_field.value = path
            else:
                self.target_path = path
                self.dst_field.value = path
            self.page.update()

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
        Path(dst).mkdir(parents=True, exist_ok=True)

        # 记住本次使用的目录，下次启动自动回填
        self.svc.settings.last_source = src
        self.svc.settings.last_target = dst
        self.svc.save_settings()

        resumable = self.svc.find_resumable(src, dst)
        if resumable:
            undone = self.svc.db.get_pending_items(resumable["id"], only_undone=True)
            if undone:
                self._show_resume_dialog(resumable["id"], len(undone), src, dst)
                return

        self._run_compare(src, dst)

    def _run_compare(self, src: str, dst: str) -> None:
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

        self._set_content(ft.Column([
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
            self._update_compare_progress(prog)

        def work():
            try:
                diff = self.svc.compare(src, dst, progress_cb=progress_cb)
                self.current_diff = diff
                self._show_confirm(src, dst, diff)
            except Exception as ex:
                self._snack(f"对比失败：{ex}", error=True)
                self._show_home()

        threading.Thread(target=work, daemon=True).start()

    def _update_compare_progress(self, prog: CompareProgress) -> None:
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
            self.page.close(dlg)
            self.current_task_id = task_id
            self._start_execution(src, dst, resume=True)

        def fresh(e):
            self.page.close(dlg)
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
                _default_button("重新开始", on_click=fresh),
                _primary_button("从断点继续",
                                icon=ft.Icons.PLAY_ARROW_ROUNDED,
                                on_click=cont),
            ],
        )
        self.page.open(dlg)

    # ========== 确认页 ==========
    def _show_confirm(self, src: str, dst: str, diff: DiffResult) -> None:
        def stat_cell(label, value, color, icon=None):
            head_children = []
            if icon is not None:
                head_children.append(ft.Icon(icon, color=color, size=16))
            head_children.append(
                ft.Text(str(value), size=T.TEXT_28,
                        weight=T.FW_MEDIUM, color=color,
                        font_family=T.FONT_MONO))
            return ft.Container(
                content=ft.Column([
                    ft.Row(head_children, spacing=T.SP_2, tight=True,
                           alignment=ft.MainAxisAlignment.CENTER),
                    _muted_text(label, size=T.TEXT_12),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=T.SP_1),
                expand=True, alignment=ft.Alignment.CENTER,
                padding=T.SP_3,
            )

        def vline():
            return ft.Container(width=1, bgcolor=T.BORDER, height=44)

        rows = []
        for it in diff.pending_items[:500]:
            kind = "success" if it.action.value == "new" else "warning"
            rows.append(ft.Container(
                content=ft.Row([
                    _badge(it.action.value, kind),
                    ft.Text(it.rel_path, size=T.TEXT_13, expand=True,
                            color=T.TEXT_TITLE, font_family=T.FONT_MONO,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    _mono_text(fmt_size(it.size), size=T.TEXT_12,
                               color=T.TEXT_TERTIARY),
                ], spacing=T.SP_3,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.symmetric(vertical=8, horizontal=T.SP_4),
                border=ft.Border(bottom=ft.BorderSide(1, T.BORDER_LIGHT)),
            ))
        if len(diff.pending_items) > 500:
            rows.append(ft.Container(
                content=_muted_text(
                    f"... 以及另外 {len(diff.pending_items) - 500} 个文件",
                    size=T.TEXT_12),
                padding=ft.Padding.symmetric(vertical=8, horizontal=T.SP_4)))

        if rows:
            list_view = ft.ListView(rows, spacing=0, expand=True)
        else:
            list_view = ft.Container(
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

        confirm_btn = _primary_button(
            "确认备份", icon=ft.Icons.PLAY_ARROW_ROUNDED,
            disabled=not diff.pending_items,
            on_click=lambda e: self._confirm_backup(src, dst, diff),
        )
        back_btn = _default_button("返回",
                                   icon=ft.Icons.ARROW_BACK_ROUNDED,
                                   on_click=lambda e: self._show_home())

        self._set_content(ft.Column([
            self._page_header("待备份清单", f"{src}  →  {dst}"),
            ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
            _card(
                ft.Row([
                    stat_cell("新增", diff.new_count, T.SUCCESS,
                              ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED),
                    vline(),
                    stat_cell("更新", diff.updated_count, T.WARNING,
                              ft.Icons.AUTORENEW_ROUNDED),
                    vline(),
                    stat_cell("跳过", diff.skipped_count, T.TEXT_TERTIARY,
                              ft.Icons.SKIP_NEXT_ROUNDED),
                    vline(),
                    stat_cell("预计传输", fmt_size(diff.pending_bytes),
                              T.PRIMARY,
                              ft.Icons.UPLOAD_OUTLINED),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ),
            ft.Container(
                content=list_view,
                bgcolor=T.BG,
                border_radius=T.RADIUS_MD,
                border=ft.Border.all(1, T.BORDER),
                expand=True,
            ),
            ft.Row([back_btn, confirm_btn],
                   alignment=ft.MainAxisAlignment.END,
                   spacing=T.SP_3),
        ], spacing=T.SP_5, expand=True))

    def _confirm_backup(self, src: str, dst: str, diff: DiffResult) -> None:
        task_id = self.svc.create_task(src, dst, diff)
        self.current_task_id = task_id
        self._start_execution(src, dst, resume=False)

    # ========== 任务进行页 ==========
    def _show_progress_view(self) -> None:
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
            on_click=lambda e: self._toggle_pause())
        self.btn_cancel = _default_button(
            "中断", icon=ft.Icons.STOP_ROUNDED,
            on_click=lambda e: self._cancel_task(),
            danger=True)

        self._set_content(ft.Column([
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
            self._update_progress(prog)

        def work():
            try:
                from vaultguard.core.executor import cleanup_temp_files
                cleanup_temp_files(dst)
                prog = self.executor.run(task_id, src, dst, resume=resume,
                                         progress_cb=progress_cb)
                self.svc._write_text_log(task_id, src, dst, prog)
                self._running = False
                self._on_finished(prog)
            except Exception as ex:
                self._running = False
                self._snack(f"执行失败：{ex}", error=True)

        threading.Thread(target=work, daemon=True).start()

    def _update_progress(self, prog: CopyProgress) -> None:
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

        if prog.current_file:
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
            self._snack("已请求中断，断点已保存，可稍后从断点继续")

    def _on_finished(self, prog: CopyProgress) -> None:
        if prog.finished:
            msg = (f"备份完成：复制 {prog.copied}，失败 {prog.failed}，"
                   f"共 {prog.total_files} 个文件。")
            self._snack(msg, error=prog.failed > 0)
        self._show_result(prog)

    def _show_result(self, prog: CopyProgress) -> None:
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

        self._set_content(ft.Column([
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
                    _default_button("返回主页",
                                    icon=ft.Icons.HOME_OUTLINED,
                                    on_click=lambda e: self._goto_home()),
                    _primary_button("查看历史",
                                    icon=ft.Icons.HISTORY_ROUNDED,
                                    on_click=lambda e: self._goto_history()),
                ], alignment=ft.MainAxisAlignment.END,
                   spacing=T.SP_3),
            ),
        ], spacing=T.SP_5))

    def _goto_home(self) -> None:
        self._nav_index = 0
        self._refresh_nav()
        self._show_home()

    def _goto_history(self) -> None:
        self._nav_index = 1
        self._refresh_nav()
        self._show_history()

    # ========== 历史记录页 ==========
    def _show_history(self) -> None:
        tasks = self.svc.list_tasks()
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

        rows = []
        kind_map = {
            "completed": "success",
            "failed": "danger",
            "paused": "warning",
            "running": "running",
            "cancelled": "warning",
        }
        for t in tasks:
            kind = kind_map.get(t["status"], "running")
            rows.append(ft.DataRow(cells=[
                ft.DataCell(_mono_text(f"#{t['id']}",
                                       size=T.TEXT_13, color=T.TEXT_TITLE)),
                ft.DataCell(_badge(t["status"], kind)),
                ft.DataCell(_mono_text(str(t["copied_files"]),
                                       color=T.SUCCESS)),
                ft.DataCell(_mono_text(str(t["failed_files"]),
                                       color=T.DANGER if t["failed_files"]
                                       else T.TEXT_TERTIARY)),
                ft.DataCell(ft.Text(fmt_time(t["start_time"]),
                                    size=T.TEXT_13, color=T.TEXT_PRIMARY)),
                ft.DataCell(ft.IconButton(
                    icon=ft.Icons.ARTICLE_OUTLINED,
                    icon_color=T.PRIMARY,
                    icon_size=18,
                    tooltip="查看详情",
                    on_click=lambda e, tid=t["id"]:
                        self._show_task_detail(tid))),
            ]))

        def col(label):
            return ft.DataColumn(
                ft.Text(label, size=T.TEXT_12,
                        color=T.TEXT_TERTIARY, weight=T.FW_MEDIUM))

        table = ft.DataTable(
            columns=[col("ID"), col("状态"), col("复制"),
                     col("失败"), col("开始时间"), col("详情")],
            rows=rows,
            heading_row_color=T.FILL,
            heading_row_height=42,
            data_row_color={"hovered": T.FILL},
            divider_thickness=1,
            border_radius=T.RADIUS_MD,
            column_spacing=28,
        )
        self._set_content(ft.Column([
            self._page_header("历史记录", f"共 {len(tasks)} 条任务记录"),
            ft.Container(height=1, bgcolor=T.BORDER_LIGHT),
            ft.Container(
                content=ft.Column([table], scroll=ft.ScrollMode.AUTO),
                bgcolor=T.BG,
                border_radius=T.RADIUS_MD,
                padding=T.SP_4,
                border=ft.Border.all(1, T.BORDER),
                expand=True,
            ),
        ], spacing=T.SP_5, expand=True))

    def _show_task_detail(self, task_id: int) -> None:
        logs = self.svc.get_file_logs(task_id)
        task = self.svc.db.get_task(task_id)
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
                "关闭", on_click=lambda e: self.page.close(dlg))],
        )
        self.page.open(dlg)

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
            label="对比文件大小", value=s.compare_size,
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

        save_btn = _primary_button("保存设置", icon=ft.Icons.SAVE_OUTLINED,
                                   on_click=lambda e: self._save_settings())

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
                    _card(data_dir_row),
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
        self.svc.save_settings()
        self._snack("设置已保存")


def main(page: ft.Page) -> None:
    VaultGuardApp(page)


def run() -> None:
    """纯桌面软件：始终使用原生窗口运行。"""
    import os
    import sys

    # 子进程模式：仅弹出原生目录选择器后退出，不启动 Flet 窗口。
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
            os.environ["FLET_VIEW_PATH"] = client_dir

    ft.app(target=main)


if __name__ == "__main__":
    run()
