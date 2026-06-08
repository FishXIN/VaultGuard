"""VaultGuard 设计系统在 Flet 桌面端的 Token 映射。

来源：VaultGuard-Design-System.md（v1.0）。
由于 Flet 不支持 CSS Variables，这里把规范中的 token 转成 Flet/Python 可消费的常量，
保持名称一致，便于跨端比对。
"""
from __future__ import annotations

import flet as ft


# ============ 1. Color ============
# 品牌主色 / 渐变端点
BLUE_PRIMARY = "#3370FF"
BLUE_START = "#3B6EF6"
CYAN_END = "#1EC6D6"

# 蓝色阶
BLUE_50 = "#EBF1FF"
BLUE_100 = "#D6E3FF"
BLUE_200 = "#ADC6FF"
BLUE_300 = "#84A9FF"
BLUE_400 = "#5B85F8"
BLUE_500 = "#3370FF"
BLUE_600 = "#2A5AD9"
BLUE_700 = "#1F44B3"
BLUE_800 = "#15308C"
BLUE_900 = "#0B1C66"

# 青色辅助
CYAN_50 = "#E6FAFC"
CYAN_200 = "#9DEAF0"
CYAN_400 = "#4FD6E2"
CYAN_500 = "#1EC6D6"
CYAN_700 = "#14939E"

# 中性
WHITE = "#FFFFFF"
BG_LIGHT = "#F7F9FC"
BG_COOL = "#E8F1FF"
GRAY_100 = "#F1F3F7"
GRAY_200 = "#E4E8F0"
GRAY_300 = "#CBD2E0"
GRAY_400 = "#9AA5BC"
GRAY_500 = "#6B7693"
GRAY_700 = "#3D4663"
GRAY_900 = "#1A2138"
INK = "#0E1428"

# 语义色
SUCCESS = "#00C566"
WARNING = "#FF9D2B"
DANGER = "#FF4D5E"
SYNCING = "#3370FF"
SUCCESS_BG = "#E6FAF0"
WARNING_BG = "#FFF4E6"
DANGER_BG = "#FFEBED"
SYNCING_BG = BLUE_50


def gradient_brand() -> ft.LinearGradient:
    """品牌主渐变（135°）"""
    return ft.LinearGradient(
        begin=ft.Alignment.TOP_LEFT,
        end=ft.Alignment.BOTTOM_RIGHT,
        colors=[BLUE_START, CYAN_END],
    )


def gradient_brand_soft() -> ft.LinearGradient:
    """品牌主渐变 hover 浅色版"""
    return ft.LinearGradient(
        begin=ft.Alignment.TOP_LEFT,
        end=ft.Alignment.BOTTOM_RIGHT,
        colors=["#5B85F8", CYAN_400],
    )


# ============ 2. Typography ============
# 字号阶梯（1.25 比例）
TEXT_XS = 12
TEXT_SM = 14
TEXT_BASE = 16
TEXT_LG = 20
TEXT_XL = 25
TEXT_2XL = 31
TEXT_3XL = 39
TEXT_4XL = 49

FW_REGULAR = ft.FontWeight.W_400
FW_MEDIUM = ft.FontWeight.W_500
FW_SEMIBOLD = ft.FontWeight.W_600
FW_BOLD = ft.FontWeight.W_700

# 字体族（与设计规范一致；Flet 走系统 fallback）
FONT_SANS = "Inter, PingFang SC, -apple-system, sans-serif"
FONT_MONO = "JetBrains Mono, SF Mono, Consolas, monospace"


# ============ 3. Spacing & Radius ============
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 24
SPACE_6 = 32
SPACE_7 = 48
SPACE_8 = 64

RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
RADIUS_XL = 24
RADIUS_2XL = 32
RADIUS_FULL = 9999


# ============ 4. Elevation ============
# Flet 的 BoxShadow 是单层；此处用同色调蓝阴影近似 CSS 多层阴影。
def shadow_sm() -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=0, blur_radius=8,
        color=ft.Colors.with_opacity(0.08, "#0E245A"),
        offset=ft.Offset(0, 2),
    )


def shadow_md() -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=0, blur_radius=16,
        color=ft.Colors.with_opacity(0.10, "#0E245A"),
        offset=ft.Offset(0, 4),
    )


def shadow_lg() -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=0, blur_radius=32,
        color=ft.Colors.with_opacity(0.12, "#0E245A"),
        offset=ft.Offset(0, 8),
    )


def glow_brand() -> ft.BoxShadow:
    """CTA hover 时的品牌发光"""
    return ft.BoxShadow(
        spread_radius=0, blur_radius=24,
        color=ft.Colors.with_opacity(0.35, BLUE_500),
        offset=ft.Offset(0, 8),
    )


# ============ 5. Motion ============
# Flet 的 ft.Animation 单位是毫秒
DUR_FAST = 180
DUR_BASE = 300
DUR_SLOW = 550

EASE_OUT = ft.AnimationCurve.EASE_OUT_CUBIC
EASE_IN_OUT = ft.AnimationCurve.EASE_IN_OUT
EASE_LINEAR = ft.AnimationCurve.LINEAR
