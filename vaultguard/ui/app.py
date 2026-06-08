"""VaultGuard Flet 图形界面（模块 5 + 6）。

视觉与交互严格遵循 VaultGuard-Design-System.md：
- 色彩：品牌蓝 #3370FF + 渐变 #3B6EF6 → #1EC6D6
- 圆角：卡片 32 / 输入框 16 / 按钮胶囊
- 阴影：带品牌蓝色调的多层柔光阴影
- 动效：克制、平滑（180/300/550ms 三档），EASE_OUT_CUBIC 主力
- 进度条：品牌渐变 + 流光（数据流动隐喻）
- 状态徽章：success / warning / danger / syncing
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

import flet as ft

from vaultguard.core.models import CopyProgress, DiffResult, TaskStatus
from vaultguard.core.service import BackupService
from . import tokens as T
from .helpers import fmt_eta, fmt_size, fmt_time


# ============ 通用 UI 工厂 ============

def _heading_gradient(text: str, size: int = T.TEXT_3XL) -> ft.ShaderMask:
    """渐变文字标题（对应规范 §2.4 .vg-heading-gradient）。"""
    return ft.ShaderMask(
        content=ft.Text(text, size=size, weight=T.FW_BOLD,
                        color=T.WHITE, font_family=T.FONT_SANS),
        blend_mode=ft.BlendMode.SRC_IN,
        shader=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=[T.BLUE_START, T.CYAN_END],
        ),
    )


def _badge(label: str, kind: str = "syncing") -> ft.Container:
    """状态徽章（规范 §5.3 .vg-badge）。kind ∈ success/warning/danger/syncing。"""
    palette = {
        "success": (T.SUCCESS, T.SUCCESS_BG),
        "warning": (T.WARNING, T.WARNING_BG),
        "danger": (T.DANGER, T.DANGER_BG),
        "syncing": (T.SYNCING, T.SYNCING_BG),
    }
    fg, bg = palette.get(kind, palette["syncing"])
    return ft.Container(
        content=ft.Row([
            ft.Container(width=6, height=6, bgcolor=fg,
                         border_radius=T.RADIUS_FULL),
            ft.Text(label, size=T.TEXT_XS, weight=T.FW_SEMIBOLD, color=fg),
        ], spacing=6, tight=True),
        bgcolor=bg,
        border_radius=T.RADIUS_FULL,
        padding=ft.Padding.symmetric(vertical=4, horizontal=12),
    )


def _primary_button(text: str, icon=None, on_click=None,
                    disabled: bool = False) -> ft.Container:
    """品牌渐变 CTA 按钮（规范 §5.1 .vg-btn--primary）。

    用 Container + GestureDetector 实现 LinearGradient 背景；
    Flet 的 FilledButton 不支持渐变填充。
    """
    children = []
    if icon is not None:
        children.append(ft.Icon(icon, color=T.WHITE, size=18))
    children.append(ft.Text(text, color=T.WHITE,
                            size=T.TEXT_BASE, weight=T.FW_SEMIBOLD))
    inner = ft.Row(children, spacing=8, tight=True,
                   alignment=ft.MainAxisAlignment.CENTER,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER)
    btn = ft.Container(
        content=inner,
        gradient=T.gradient_brand(),
        border_radius=T.RADIUS_FULL,
        padding=ft.Padding.symmetric(vertical=0, horizontal=28),
        height=48,
        alignment=ft.Alignment.CENTER,
        shadow=T.shadow_md(),
        animate=ft.Animation(T.DUR_FAST, T.EASE_OUT),
        animate_scale=ft.Animation(T.DUR_FAST, T.EASE_OUT),
        on_click=(None if disabled else on_click),
        opacity=0.45 if disabled else 1.0,
        ink=False,
    )

    def _hover(e: ft.HoverEvent) -> None:
        if disabled:
            return
        if e.data == "true":
            btn.gradient = T.gradient_brand_soft()
            btn.shadow = T.glow_brand()
            btn.scale = ft.Scale(1.02)
        else:
            btn.gradient = T.gradient_brand()
            btn.shadow = T.shadow_md()
            btn.scale = ft.Scale(1.0)
        btn.update()

    btn.on_hover = _hover
    return btn


def _ghost_button(text: str, icon=None, on_click=None,
                  danger: bool = False) -> ft.OutlinedButton:
    """次按钮（规范 §5.1 .vg-btn--ghost）。"""
    color = T.DANGER if danger else T.BLUE_500
    border = ft.BorderSide(1.5, T.DANGER if danger else T.BLUE_200)
    return ft.OutlinedButton(
        text=text,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            color=color,
            side=border,
            shape=ft.RoundedRectangleBorder(radius=T.RADIUS_FULL),
            padding=ft.Padding.symmetric(vertical=14, horizontal=22),
            text_style=ft.TextStyle(size=T.TEXT_SM, weight=T.FW_SEMIBOLD),
        ),
    )


def _card(*controls, padding: int = T.SPACE_6,
          expand: Optional[bool] = None) -> ft.Container:
    """卡片容器（规范 §5.2 .vg-card）。"""
    column = ft.Column(list(controls), spacing=T.SPACE_3, tight=True)
    return ft.Container(
        content=column,
        bgcolor=T.WHITE,
        border_radius=T.RADIUS_2XL,
        padding=padding,
        border=ft.Border.all(1, T.GRAY_100),
        shadow=T.shadow_md(),
        animate=ft.Animation(T.DUR_BASE, T.EASE_OUT),
        expand=expand,
    )


def _section_title(text: str) -> ft.Text:
    return ft.Text(text, size=T.TEXT_LG, weight=T.FW_SEMIBOLD,
                   color=T.GRAY_900, font_family=T.FONT_SANS)


def _muted_text(text: str, size: int = T.TEXT_SM) -> ft.Text:
    return ft.Text(text, size=size, color=T.GRAY_500,
                   font_family=T.FONT_SANS)


def _mono_text(text: str, size: int = T.TEXT_SM,
               color: str = T.GRAY_700) -> ft.Text:
    """数据/容量/速率展示（规范 §2.1 推荐 mono 字体）。"""
    return ft.Text(text, size=size, color=color, font_family=T.FONT_MONO)


def _progress_track(height: int = 8) -> ft.Container:
    """流光渐变进度条容器（规范 §5.4）；通过覆盖一个 gradient bar 实现。"""
    return ft.Container(
        bgcolor=T.GRAY_200,
        height=height,
        border_radius=T.RADIUS_FULL,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
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
        self.source_path = ""
        self.target_path = ""
        self._running = False

        self._setup_page()
        self._build_layout()
        self._show_home()

    # ---------- 页面基础 ----------
    def _setup_page(self) -> None:
        p = self.page
        p.title = "VaultGuard · 增量备份"
        p.bgcolor = T.BG_LIGHT
        p.theme_mode = ft.ThemeMode.LIGHT
        p.theme = ft.Theme(
            color_scheme_seed=T.BLUE_PRIMARY,
            font_family="-apple-system",
            visual_density=ft.VisualDensity.COMFORTABLE,
        )
        p.window.width = 1120
        p.window.height = 760
        p.window.min_width = 960
        p.window.min_height = 640
        p.padding = 0

    def _build_layout(self) -> None:
        # 左侧导航（卡片化、大圆角、品牌蓝选中态）
        self.nav = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=96,
            min_extended_width=180,
            bgcolor=T.WHITE,
            indicator_color=T.BLUE_50,
            indicator_shape=ft.RoundedRectangleBorder(radius=T.RADIUS_LG),
            selected_label_text_style=ft.TextStyle(
                color=T.BLUE_500, weight=T.FW_SEMIBOLD, size=T.TEXT_SM),
            unselected_label_text_style=ft.TextStyle(
                color=T.GRAY_500, size=T.TEXT_SM),
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.HOME_OUTLINED,
                    selected_icon=ft.Icons.HOME_ROUNDED, label="主页"),
                ft.NavigationRailDestination(
                    icon=ft.Icons.HISTORY_OUTLINED,
                    selected_icon=ft.Icons.HISTORY_ROUNDED, label="历史"),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS_ROUNDED, label="设置"),
            ],
            on_change=self._on_nav_change,
        )

        nav_card = ft.Container(
            content=self.nav,
            bgcolor=T.WHITE,
            border_radius=ft.BorderRadius.only(top_right=T.RADIUS_2XL,
                                                bottom_right=T.RADIUS_2XL),
            shadow=T.shadow_sm(),
        )

        self.content = ft.Container(
            expand=True,
            padding=ft.Padding.symmetric(vertical=T.SPACE_5, horizontal=T.SPACE_6),
            bgcolor=T.BG_LIGHT,
        )

        self.page.add(
            ft.Row(
                [nav_card, self.content],
                expand=True,
                spacing=0,
            )
        )

    def _on_nav_change(self, e) -> None:
        idx = e.control.selected_index
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
                ft.Text(msg, color=T.WHITE, weight=T.FW_MEDIUM),
                bgcolor=T.DANGER if error else T.SUCCESS,
                shape=ft.RoundedRectangleBorder(radius=T.RADIUS_LG),
            )
        )

    def _page_header(self, title: str, subtitle: Optional[str] = None) -> ft.Column:
        items = [_heading_gradient(title, size=T.TEXT_2XL)]
        if subtitle:
            items.append(_muted_text(subtitle, size=T.TEXT_SM))
        return ft.Column(items, spacing=T.SPACE_1, tight=True)

    # ========== 主页 ==========
    def _show_home(self) -> None:
        self.src_field = ft.TextField(
            label="源目录",
            value=self.source_path,
            hint_text="可直接输入路径或点右侧按钮选择，例如 /Users/you/Documents",
            on_change=lambda e: setattr(self, "source_path", e.control.value),
            expand=True,
            border_radius=T.RADIUS_LG,
            border_color=T.GRAY_200,
            focused_border_color=T.BLUE_500,
            cursor_color=T.BLUE_500,
            text_size=T.TEXT_SM,
            content_padding=ft.Padding.symmetric(vertical=14, horizontal=16),
        )
        self.dst_field = ft.TextField(
            label="目标目录",
            value=self.target_path,
            hint_text="可直接输入路径或点右侧按钮选择，例如 /Volumes/Backup/MyData",
            on_change=lambda e: setattr(self, "target_path", e.control.value),
            expand=True,
            border_radius=T.RADIUS_LG,
            border_color=T.GRAY_200,
            focused_border_color=T.BLUE_500,
            cursor_color=T.BLUE_500,
            text_size=T.TEXT_SM,
            content_padding=ft.Padding.symmetric(vertical=14, horizontal=16),
        )

        def _picker_btn(is_source: bool) -> ft.Container:
            b = ft.Container(
                content=ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED,
                                color=T.BLUE_500, size=20),
                width=44, height=44,
                bgcolor=T.BLUE_50,
                border_radius=T.RADIUS_MD,
                alignment=ft.Alignment.CENTER,
                tooltip="选择源目录" if is_source else "选择目标目录",
                on_click=lambda e, s=is_source: self._pick_dir(s),
                animate=ft.Animation(T.DUR_FAST, T.EASE_OUT),
            )

            def _hover(e: ft.HoverEvent, ctrl=b) -> None:
                ctrl.bgcolor = T.BLUE_100 if e.data == "true" else T.BLUE_50
                ctrl.update()

            b.on_hover = _hover
            return b

        feature_chip = lambda txt, ic: ft.Container(
            content=ft.Row([
                ft.Icon(ic, color=T.BLUE_500, size=14),
                ft.Text(txt, size=T.TEXT_XS,
                        color=T.GRAY_700, weight=T.FW_MEDIUM),
            ], spacing=6, tight=True),
            bgcolor=T.BLUE_50,
            border_radius=T.RADIUS_FULL,
            padding=ft.Padding.symmetric(vertical=6, horizontal=12),
        )

        self._set_content(ft.Column([
            self._page_header("VaultGuard · 本地硬盘增量备份",
                              "文件安全第一 · 增量优先 · 先选后执行 · 可中断续传"),
            ft.Row([
                feature_chip("文件安全", ft.Icons.SHIELD_OUTLINED),
                feature_chip("增量优先", ft.Icons.BOLT_OUTLINED),
                feature_chip("断点续传", ft.Icons.REPLAY_ROUNDED),
                feature_chip("原生体验", ft.Icons.APPLE_ROUNDED),
            ], spacing=T.SPACE_2, wrap=True),
            ft.Container(height=T.SPACE_2),
            _card(
                _section_title("选择目录"),
                _muted_text("支持本地路径和外接硬盘，进入下一步会先做对比再执行。",
                            size=T.TEXT_XS),
                ft.Container(height=T.SPACE_1),
                ft.Row([self.src_field, _picker_btn(True)],
                       vertical_alignment=ft.CrossAxisAlignment.END,
                       spacing=T.SPACE_3),
                ft.Row([self.dst_field, _picker_btn(False)],
                       vertical_alignment=ft.CrossAxisAlignment.END,
                       spacing=T.SPACE_3),
                ft.Container(height=T.SPACE_2),
                ft.Row([
                    _primary_button("开始对比",
                                    icon=ft.Icons.COMPARE_ARROWS_ROUNDED,
                                    on_click=lambda e: self._do_compare()),
                ], alignment=ft.MainAxisAlignment.END),
            ),
        ], spacing=T.SPACE_4, scroll=ft.ScrollMode.AUTO))

    def _pick_dir(self, is_source: bool) -> None:
        # 通过系统自带 osascript 弹出原生访达目录选择框，由系统进程托管，
        # 不在 Flet 线程直接碰 AppKit，也不另起窗口进程。
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

        resumable = self.svc.find_resumable(src, dst)
        if resumable:
            undone = self.svc.db.get_pending_items(resumable["id"], only_undone=True)
            if undone:
                self._show_resume_dialog(resumable["id"], len(undone), src, dst)
                return

        self._run_compare(src, dst)

    def _run_compare(self, src: str, dst: str) -> None:
        # 全屏卡片化的"对比中"提示
        spinner = ft.Container(
            width=72, height=72,
            border_radius=T.RADIUS_FULL,
            gradient=T.gradient_brand(),
            shadow=T.glow_brand(),
            content=ft.Container(
                width=58, height=58,
                bgcolor=T.WHITE,
                border_radius=T.RADIUS_FULL,
                alignment=ft.Alignment.CENTER,
                content=ft.ProgressRing(
                    width=28, height=28, stroke_width=3, color=T.BLUE_500),
            ),
            alignment=ft.Alignment.CENTER,
        )
        self._set_content(ft.Column([
            self._page_header("正在对比", "递归扫描源目录并与目标目录对比 ..."),
            ft.Container(height=T.SPACE_4),
            _card(
                ft.Row([spinner], alignment=ft.MainAxisAlignment.CENTER),
                ft.Container(height=T.SPACE_3),
                ft.Row([_badge("同步中", "syncing")],
                       alignment=ft.MainAxisAlignment.CENTER),
                ft.Container(height=T.SPACE_2),
                _muted_text("文件较多时可能需要一会儿，请稍候。",
                            size=T.TEXT_SM),
                padding=T.SPACE_7,
            ),
        ], spacing=T.SPACE_4))

        def work():
            try:
                diff = self.svc.compare(src, dst)
                self.current_diff = diff
                self._show_confirm(src, dst, diff)
            except Exception as ex:
                self._snack(f"对比失败：{ex}", error=True)
                self._show_home()

        threading.Thread(target=work, daemon=True).start()

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
                          weight=T.FW_BOLD, color=T.GRAY_900),
            content=ft.Text(
                f"任务 #{task_id} 还有 {undone} 个文件未完成。\n"
                "您可以从断点继续，或重新开始对比。",
                color=T.GRAY_700),
            shape=ft.RoundedRectangleBorder(radius=T.RADIUS_XL),
            actions=[
                _ghost_button("重新开始", on_click=fresh),
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
                head_children.append(ft.Icon(icon, color=color, size=18))
            head_children.append(
                ft.Text(str(value), size=T.TEXT_2XL,
                        weight=T.FW_BOLD, color=color,
                        font_family=T.FONT_MONO))
            return ft.Container(
                content=ft.Column([
                    ft.Row(head_children, spacing=8, tight=True,
                           alignment=ft.MainAxisAlignment.CENTER),
                    _muted_text(label, size=T.TEXT_XS),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4),
                expand=True, alignment=ft.Alignment.CENTER,
                padding=T.SPACE_3,
            )

        def vline():
            return ft.Container(width=1, bgcolor=T.GRAY_200, height=44)

        rows = []
        for it in diff.pending_items[:500]:
            kind = "success" if it.action.value == "new" else "warning"
            rows.append(ft.Row([
                _badge(it.action.value, kind),
                ft.Text(it.rel_path, size=T.TEXT_SM, expand=True,
                        color=T.GRAY_700,
                        overflow=ft.TextOverflow.ELLIPSIS),
                _mono_text(fmt_size(it.size), size=T.TEXT_XS,
                           color=T.GRAY_500),
            ], spacing=T.SPACE_3,
               vertical_alignment=ft.CrossAxisAlignment.CENTER))
        if len(diff.pending_items) > 500:
            rows.append(_muted_text(
                f"... 以及另外 {len(diff.pending_items) - 500} 个文件",
                size=T.TEXT_XS))

        if rows:
            list_view = ft.ListView(rows, spacing=T.SPACE_2,
                                    expand=True, padding=T.SPACE_3)
        else:
            list_view = ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED,
                            color=T.SUCCESS, size=40),
                    ft.Text("没有需要备份的文件", weight=T.FW_SEMIBOLD,
                            color=T.GRAY_900, size=T.TEXT_LG),
                    _muted_text("目标目录已经是最新的副本。",
                                size=T.TEXT_SM),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                   spacing=T.SPACE_2),
                padding=T.SPACE_7,
                alignment=ft.Alignment.CENTER,
            )

        confirm_btn = _primary_button(
            "确认备份", icon=ft.Icons.PLAY_ARROW_ROUNDED,
            disabled=not diff.pending_items,
            on_click=lambda e: self._confirm_backup(src, dst, diff),
        )
        back_btn = _ghost_button("返回",
                                 icon=ft.Icons.ARROW_BACK_ROUNDED,
                                 on_click=lambda e: self._show_home())

        self._set_content(ft.Column([
            self._page_header("待备份清单",
                              f"{src}  →  {dst}"),
            _card(
                ft.Row([
                    stat_cell("新增", diff.new_count, T.SUCCESS,
                              ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED),
                    vline(),
                    stat_cell("更新", diff.updated_count, T.WARNING,
                              ft.Icons.AUTORENEW_ROUNDED),
                    vline(),
                    stat_cell("跳过", diff.skipped_count, T.GRAY_500,
                              ft.Icons.SKIP_NEXT_ROUNDED),
                    vline(),
                    stat_cell("预计传输", fmt_size(diff.pending_bytes),
                              T.BLUE_500,
                              ft.Icons.UPLOAD_ROUNDED),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ),
            ft.Container(
                content=list_view,
                bgcolor=T.WHITE,
                border_radius=T.RADIUS_2XL,
                padding=T.SPACE_3,
                border=ft.Border.all(1, T.GRAY_100),
                shadow=T.shadow_sm(),
                expand=True,
            ),
            ft.Row([back_btn, confirm_btn],
                   alignment=ft.MainAxisAlignment.END,
                   spacing=T.SPACE_3),
        ], spacing=T.SPACE_4, expand=True))

    def _confirm_backup(self, src: str, dst: str, diff: DiffResult) -> None:
        task_id = self.svc.create_task(src, dst, diff)
        self.current_task_id = task_id
        self._start_execution(src, dst, resume=False)

    # ========== 任务进行页 ==========
    def _show_progress_view(self) -> None:
        # 流光渐变进度条：track + fill
        self.pb_track = ft.Container(
            bgcolor=T.GRAY_200,
            height=10,
            border_radius=T.RADIUS_FULL,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            expand=True,
        )
        self.pb_fill = ft.Container(
            gradient=T.gradient_brand(),
            border_radius=T.RADIUS_FULL,
            height=10,
            width=0,
            animate=ft.Animation(T.DUR_BASE, T.EASE_OUT),
        )
        # fill 套在 track 内（左对齐）
        self.pb_track.content = ft.Row([self.pb_fill], spacing=0)

        self.lbl_pct = ft.Text(
            "0%", size=T.TEXT_3XL, weight=T.FW_BOLD,
            color=T.BLUE_500, font_family=T.FONT_MONO)
        self.lbl_file = ft.Text(
            "准备中 ...", size=T.TEXT_SM, color=T.GRAY_700,
            overflow=ft.TextOverflow.ELLIPSIS, font_family=T.FONT_MONO)
        self.lbl_stat = ft.Text("", size=T.TEXT_SM, color=T.GRAY_700)
        self.lbl_speed = _mono_text("", size=T.TEXT_SM, color=T.GRAY_500)
        self.log_view = ft.ListView([], spacing=4, expand=True,
                                    padding=T.SPACE_3, auto_scroll=True)

        self.btn_pause = _ghost_button(
            "暂停", icon=ft.Icons.PAUSE_ROUNDED,
            on_click=lambda e: self._toggle_pause())
        self.btn_cancel = _ghost_button(
            "中断", icon=ft.Icons.STOP_ROUNDED,
            on_click=lambda e: self._cancel_task(),
            danger=True)

        self._set_content(ft.Column([
            self._page_header("备份进行中"),
            _card(
                ft.Row([
                    ft.Column([
                        self.lbl_pct,
                        ft.Row([_badge("同步中", "syncing"), self.lbl_stat],
                               spacing=T.SPACE_2,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        self.lbl_speed,
                    ], spacing=T.SPACE_1, expand=True),
                    ft.Row([self.btn_pause, self.btn_cancel],
                           spacing=T.SPACE_2),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(height=T.SPACE_2),
                self.pb_track,
                ft.Row([
                    ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED,
                            size=14, color=T.GRAY_400),
                    self.lbl_file,
                ], spacing=8),
            ),
            _section_title("实时日志"),
            ft.Container(
                content=self.log_view,
                bgcolor=T.INK,
                border_radius=T.RADIUS_2XL,
                padding=T.SPACE_2,
                expand=True,
                shadow=T.shadow_sm(),
            ),
        ], spacing=T.SPACE_4, expand=True))

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
        # 用 LayoutBuilder 不便，这里用百分比宽度近似：track 内 fill 用相对 width
        try:
            track_width = self.pb_track.width or 0
        except Exception:
            track_width = 0
        # Flet 没有现成的相对宽度；用 expand=False 并通过 page 的当前宽度 - 容器 padding 大致估算。
        # 退而求其次：让 fill 占据 fraction 由父 Row 的 expand 控制。
        # 简化方案：直接用 ProgressBar 的语义，通过 fill 的 expand 来按比例占位。
        self.pb_fill.width = None
        self.pb_fill.expand = max(pct, 0.001) if pct < 1 else 1
        # 用父 Row 的另一个空白 spacer 来占据剩余
        # 这里采用更稳妥的方式：直接把 track.content 替换为 Row[fill(expand=pct), spacer(expand=1-pct)]
        if pct < 1.0:
            spacer_expand = max(1.0 - pct, 0.001)
            self.pb_track.content = ft.Row([
                ft.Container(gradient=T.gradient_brand(),
                             height=10, expand=pct,
                             border_radius=T.RADIUS_FULL),
                ft.Container(expand=spacer_expand),
            ], spacing=0)
        else:
            self.pb_track.content = ft.Container(
                gradient=T.gradient_brand(),
                height=10, expand=True,
                border_radius=T.RADIUS_FULL)

        self.lbl_pct.value = f"{pct * 100:.0f}%"
        self.lbl_stat.value = (
            f"{prog.processed_files}/{prog.total_files} 文件 · "
            f"复制 {prog.copied} · 失败 {prog.failed}")
        self.lbl_speed.value = (
            f"{fmt_size(prog.speed_bps)}/s · 剩余 {fmt_eta(prog.eta_seconds)}")
        self.lbl_file.value = prog.current_file or "..."

        if prog.current_file:
            self.log_view.controls.append(
                ft.Text(f"✓ {prog.current_file}", size=11,
                        color=T.CYAN_400, font_family=T.FONT_MONO))
            if len(self.log_view.controls) > 1000:
                self.log_view.controls.pop(0)
        try:
            self.page.update()
        except Exception:
            pass

    def _toggle_pause(self) -> None:
        if not self.executor:
            return
        if self.executor.is_paused:
            self.executor.resume()
            self.btn_pause.text = "暂停"
            self.btn_pause.icon = ft.Icons.PAUSE_ROUNDED
        else:
            self.executor.pause()
            self.btn_pause.text = "继续"
            self.btn_pause.icon = ft.Icons.PLAY_ARROW_ROUNDED
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
            kind, color, icon = "success", T.SUCCESS, ft.Icons.VERIFIED_ROUNDED
            title = "备份完成"
        elif prog.finished:
            kind, color, icon = "warning", T.WARNING, ft.Icons.WARNING_AMBER_ROUNDED
            title = "备份完成（有失败项）"
        else:
            kind, color, icon = "danger", T.DANGER, ft.Icons.STOP_CIRCLE_OUTLINED
            title = "任务已中断"

        big_icon = ft.Container(
            width=72, height=72,
            border_radius=T.RADIUS_FULL,
            bgcolor=ft.Colors.with_opacity(0.12, color),
            content=ft.Icon(icon, size=36, color=color),
            alignment=ft.Alignment.CENTER,
        )

        def kv(label, value, mono=True):
            return ft.Row([
                _muted_text(label, size=T.TEXT_SM),
                ft.Container(expand=True),
                (_mono_text(str(value), size=T.TEXT_SM, color=T.GRAY_900)
                 if mono else
                 ft.Text(str(value), size=T.TEXT_SM,
                         color=T.GRAY_900, weight=T.FW_SEMIBOLD)),
            ])

        self._set_content(ft.Column([
            self._page_header("备份结果"),
            _card(
                ft.Row([
                    big_icon,
                    ft.Column([
                        ft.Text(title, size=T.TEXT_XL, weight=T.FW_BOLD,
                                color=T.GRAY_900),
                        _badge({"success": "成功", "warning": "完成（有失败）",
                                "danger": "已中断"}[kind], kind),
                    ], spacing=T.SPACE_2),
                ], spacing=T.SPACE_4,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(color=T.GRAY_100),
                kv("复制", f"{prog.copied} 个"),
                kv("失败", f"{prog.failed} 个"),
                kv("传输", fmt_size(prog.transferred_bytes)),
                ft.Container(height=T.SPACE_2),
                ft.Row([
                    _ghost_button("返回主页",
                                  icon=ft.Icons.HOME_ROUNDED,
                                  on_click=lambda e: self._show_home()),
                    _primary_button("查看历史",
                                    icon=ft.Icons.HISTORY_ROUNDED,
                                    on_click=lambda e: self._goto_history()),
                ], alignment=ft.MainAxisAlignment.END,
                   spacing=T.SPACE_3),
            ),
        ], spacing=T.SPACE_4))

    def _goto_history(self) -> None:
        self.nav.selected_index = 1
        self._show_history()

    # ========== 历史记录页 ==========
    def _show_history(self) -> None:
        tasks = self.svc.list_tasks()
        if not tasks:
            self._set_content(ft.Column([
                self._page_header("历史记录"),
                _card(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.INBOX_ROUNDED,
                                    color=T.GRAY_400, size=40),
                            _muted_text("暂无历史任务", size=T.TEXT_SM),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                           spacing=T.SPACE_2),
                        padding=T.SPACE_7,
                        alignment=ft.Alignment.CENTER,
                    ),
                ),
            ], spacing=T.SPACE_4))
            return

        rows = []
        kind_map = {
            "completed": "success",
            "failed": "danger",
            "paused": "warning",
            "running": "syncing",
            "cancelled": "warning",
        }
        for t in tasks:
            kind = kind_map.get(t["status"], "syncing")
            rows.append(ft.DataRow(cells=[
                ft.DataCell(_mono_text(f"#{t['id']}",
                                       size=T.TEXT_SM, color=T.GRAY_900)),
                ft.DataCell(_badge(t["status"], kind)),
                ft.DataCell(_mono_text(str(t["copied_files"]),
                                       color=T.SUCCESS)),
                ft.DataCell(_mono_text(str(t["failed_files"]),
                                       color=T.DANGER if t["failed_files"]
                                       else T.GRAY_500)),
                ft.DataCell(ft.Text(fmt_time(t["start_time"]),
                                    size=T.TEXT_SM, color=T.GRAY_700)),
                ft.DataCell(ft.IconButton(
                    icon=ft.Icons.ARTICLE_OUTLINED,
                    icon_color=T.BLUE_500,
                    tooltip="查看详情",
                    on_click=lambda e, tid=t["id"]:
                        self._show_task_detail(tid))),
            ]))

        def col(label):
            return ft.DataColumn(
                ft.Text(label, size=T.TEXT_XS,
                        color=T.GRAY_500, weight=T.FW_SEMIBOLD))

        table = ft.DataTable(
            columns=[col("ID"), col("状态"), col("复制"),
                     col("失败"), col("开始时间"), col("详情")],
            rows=rows,
            heading_row_color=T.BG_COOL,
            heading_row_height=42,
            data_row_color={"hovered": T.BG_COOL},
            divider_thickness=0.5,
            column_spacing=28,
        )
        self._set_content(ft.Column([
            self._page_header("历史记录",
                              f"共 {len(tasks)} 条任务记录"),
            ft.Container(
                content=ft.Column([table], scroll=ft.ScrollMode.AUTO),
                bgcolor=T.WHITE,
                border_radius=T.RADIUS_2XL,
                padding=T.SPACE_4,
                border=ft.Border.all(1, T.GRAY_100),
                shadow=T.shadow_md(),
                expand=True,
            ),
        ], spacing=T.SPACE_4, expand=True))

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
                ft.Text(lg["file_path"], size=T.TEXT_SM, expand=True,
                        color=T.GRAY_700,
                        overflow=ft.TextOverflow.ELLIPSIS),
                _muted_text(lg["reason"], size=T.TEXT_XS),
            ], spacing=T.SPACE_2))
        if not items:
            items = [_muted_text("无文件日志")]

        content = ft.Container(
            content=ft.ListView(items, spacing=T.SPACE_1, padding=T.SPACE_3),
            width=680, height=440,
        )
        dlg = ft.AlertDialog(
            title=ft.Text(
                f"任务 #{task_id} 详情"
                + (f" · {task['status']}" if task else ""),
                weight=T.FW_BOLD, color=T.GRAY_900),
            content=content,
            shape=ft.RoundedRectangleBorder(radius=T.RADIUS_XL),
            actions=[_ghost_button(
                "关闭", on_click=lambda e: self.page.close(dlg))],
        )
        self.page.open(dlg)

    # ========== 设置页 ==========
    def _show_settings(self) -> None:
        s = self.svc.settings

        def _tf(label, value, **kw) -> ft.TextField:
            return ft.TextField(
                label=label, value=value,
                border_radius=T.RADIUS_LG,
                border_color=T.GRAY_200,
                focused_border_color=T.BLUE_500,
                cursor_color=T.BLUE_500,
                text_size=T.TEXT_SM,
                content_padding=ft.Padding.symmetric(vertical=12, horizontal=14),
                **kw,
            )

        self.f_tolerance = _tf(
            "mtime 容差（秒）", str(s.mtime_tolerance),
            width=220, dense=True,
            keyboard_type=ft.KeyboardType.NUMBER)
        self.f_compare_size = ft.Switch(
            label="对比文件大小", value=s.compare_size,
            active_color=T.BLUE_500)
        self.f_verify_hash = ft.Switch(
            label="复制后做 hash 完整性校验（更安全，更慢）",
            value=s.verify_hash, active_color=T.BLUE_500)
        self.f_delete_sync = ft.Switch(
            label="删除同步（危险，默认关闭）",
            value=s.delete_sync, active_color=T.DANGER)
        self.f_use_recycle = ft.Switch(
            label="删除时移入回收区而非物理删除",
            value=s.use_recycle, active_color=T.BLUE_500)
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
                    color=T.GRAY_400, size=18),
            _muted_text(f"数据/日志/配置位置：{self.svc.data_dir}",
                        size=T.TEXT_XS),
        ], spacing=T.SPACE_2)

        save_btn = _primary_button("保存设置", icon=ft.Icons.SAVE_ROUNDED,
                                   on_click=lambda e: self._save_settings())

        self._set_content(ft.Column([
            self._page_header("设置", "调整对比策略与文件安全规则"),
            _card(
                _section_title("对比策略"),
                self.f_tolerance,
                self.f_compare_size,
            ),
            _card(
                _section_title("文件安全"),
                self.f_verify_hash,
                self.f_retry,
                ft.Divider(color=T.GRAY_100),
                ft.Row([
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED,
                            color=T.DANGER, size=16),
                    ft.Text("删除策略（遵循文件安全原则）",
                            size=T.TEXT_SM, weight=T.FW_SEMIBOLD,
                            color=T.DANGER),
                ], spacing=T.SPACE_2),
                self.f_delete_sync,
                self.f_use_recycle,
            ),
            _card(
                _section_title("排除规则"),
                self.f_exclude,
            ),
            _card(data_dir_row),
            ft.Row([save_btn], alignment=ft.MainAxisAlignment.END),
        ], spacing=T.SPACE_4, scroll=ft.ScrollMode.AUTO))

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
