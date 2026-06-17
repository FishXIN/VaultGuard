"""VaultGuard 设计系统在桌面端的 Token 映射。

来源：VaultGuard-Design-System.md（v2.0 · 火山引擎 / Arco 极简风）。
由于桌面端不支持 CSS Variables，这里把规范中的 token 转成 Python 可消费的常量，
保持名称一致，便于跨端比对。

设计基准：黑白灰为主、单一克制黑、小圆角（4–6px）、极轻阴影（仅浮层）、零多余特效。
"""
from __future__ import annotations

from .runtime import ft


# ============ 1. 颜色 ============
# 颜色支持浅色 / 深色双主题：下方两套调色板在运行时由 apply_theme() 切换。
# 由于桌面端所有控件在构建时直接读取 T.PRIMARY 等模块常量，切换主题时需
# 先调用 apply_theme() 改写这些全局常量，再重建界面，新配色即整体生效。
#
#   1.1 主色（唯一强调色）：浅色为近黑、深色反相为近白，使实心主按钮在两种
#       主题下都保持「填充强调色 + BG 反差文字」的对比关系。
#   1.2 中性色（文本 / 边框 / 填充 / 背景）。
#   1.3 状态色（备份语义，低饱和），深色下背景变体改为深色微着色。
_LIGHT = dict(
    PRIMARY="#1D2129", PRIMARY_HOVER="#4E5969", PRIMARY_ACTIVE="#000000",
    PRIMARY_BG="#E5E6EB",  # 浅灰底：选中行、轻量标签
    TEXT_TITLE="#1D2129", TEXT_PRIMARY="#4E5969", TEXT_TERTIARY="#86909C",
    TEXT_DISABLED="#C9CDD4",
    BORDER="#E5E6EB", BORDER_LIGHT="#F2F3F5",
    FILL="#F7F8FA", FILL_HOVER="#F2F3F5", FILL_ACTIVE="#C9CDD4",
    BG="#FFFFFF",
    SUCCESS="#00B42A", SUCCESS_BG="#E8FFEA",
    WARNING="#FF7D00", WARNING_BG="#FFF7E8",
    DANGER="#F53F3F", DANGER_BG="#FFECE8",
    RUNNING="#4E5969", RUNNING_BG="#E5E6EB",
)
_DARK = dict(
    PRIMARY="#E8EAED", PRIMARY_HOVER="#C9CDD4", PRIMARY_ACTIVE="#FFFFFF",
    PRIMARY_BG="#2E2E33",
    TEXT_TITLE="#F7F8FA", TEXT_PRIMARY="#C9CDD4", TEXT_TERTIARY="#86909C",
    TEXT_DISABLED="#4E5969",
    BORDER="#333338", BORDER_LIGHT="#2A2A2E",
    FILL="#232326", FILL_HOVER="#2A2A2E", FILL_ACTIVE="#3A3A40",
    BG="#17171A",
    SUCCESS="#23C343", SUCCESS_BG="#1B3326",
    WARNING="#FF9A2E", WARNING_BG="#332512",
    DANGER="#F76965", DANGER_BG="#3A1E1E",
    RUNNING="#C9CDD4", RUNNING_BG="#2E2E33",
)


def apply_theme(dark: bool) -> None:
    """切换调色板：改写本模块的颜色全局常量。

    必须在重建界面（重新构建控件树）之前调用，已构建的控件不会自动变色。
    """
    globals().update(_DARK if dark else _LIGHT)


# 默认浅色：导入即生效，保证 from . import tokens as T 后各颜色常量可用。
apply_theme(False)


# ============ 2. 字体 ============
# 为让 macOS 与 Windows 字形、字重完全一致，统一打包并使用思源黑体
# （Noto Sans SC 可变字体，含 100–900 全字重，免费可商用 OFL）。
# 通过 page.fonts 注册后，两端都按同一字体渲染，彻底消除「Windows 上
# medium/semibold 字重缺失被回退成细体」「PingFang 与雅黑字形不同」的问题。
# 字体文件位于 assets/fonts/NotoSansSC.ttf，由运行时 assets_dir 提供。
FONT_FAMILY_NAME = "Noto Sans SC"
FONT_ASSET_REL = "fonts/NotoSansSC.ttf"
FONT_SANS = FONT_FAMILY_NAME
# 等宽场景（路径 / 容量 / 速率）仍用各平台系统等宽拉丁字体，数字宽度一致。
import sys as _sys

FONT_MONO = "Consolas" if _sys.platform.startswith("win") else "SF Mono"

# 字号阶梯（桌面密度，紧凑克制）
TEXT_12 = 12  # 标签、辅助
TEXT_13 = 13  # 次要正文 / 表格
TEXT_14 = 14  # 正文基准
TEXT_16 = 16  # 小标题
TEXT_20 = 20  # 区块标题
TEXT_28 = 28  # 页面主标题（最大）

FW_REGULAR = ft.FontWeight.W_400
FW_MEDIUM = ft.FontWeight.W_500  # 标题/强调默认用 medium
FW_SEMIBOLD = ft.FontWeight.W_600


# ============ 3. 间距与圆角 ============
# 间距 4px 基准
SP_1 = 4
SP_2 = 8
SP_3 = 12
SP_4 = 16
SP_5 = 20
SP_6 = 24
SP_8 = 32
SP_10 = 40

# 圆角——小而克制（Arco 风格）
RADIUS_SM = 2  # 标签、输入框内元素
RADIUS = 4     # 按钮、输入框、默认
RADIUS_MD = 6  # 卡片 / 弹窗
RADIUS_LG = 8  # 大容器（少用）


# ============ 4. 阴影（极轻，仅浮层使用）============
def shadow_sm() -> ft.BoxShadow:
    """下拉、tooltip。"""
    return ft.BoxShadow(
        spread_radius=0, blur_radius=4,
        color=ft.Colors.with_opacity(0.06, "#000000"),
        offset=ft.Offset(0, 1),
    )


def shadow_md() -> ft.BoxShadow:
    """弹窗、抽屉。"""
    return ft.BoxShadow(
        spread_radius=0, blur_radius=8,
        color=ft.Colors.with_opacity(0.08, "#000000"),
        offset=ft.Offset(0, 2),
    )


# ============ 5. 布局 ============
SIDEBAR_W = 156
HEADER_H = 44


# ============ 6. 动效（极简）============
# ft.Animation 单位是毫秒
DUR_FAST = 150  # hover / 颜色过渡
DUR_BASE = 250  # 弹窗 / 抽屉出现

EASE = ft.AnimationCurve.EASE_IN_OUT  # 标准缓动 cubic-bezier(.4,0,.2,1)
EASE_LINEAR = ft.AnimationCurve.LINEAR
