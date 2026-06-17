# VaultGuard · 本地硬盘增量备份

[![Release](https://img.shields.io/github/v/release/FishXIN/VaultGuard?display_name=tag)](https://github.com/FishXIN/VaultGuard/releases)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-1f2328)](https://github.com/FishXIN/VaultGuard/releases)
[![Tests](https://img.shields.io/badge/tests-7%20passed-2ea043)](https://github.com/FishXIN/VaultGuard)

以「文件安全」为最高优先级的本地硬盘增量备份工具（Windows / macOS）。提供原生桌面应用体验。

通过对比文件修改时间识别需备份文件，**先选清单、确认后再执行**，已备份且未变更的文件自动跳过；支持断点续传，全程可视化进度与完整日志。

## 发布与更新

- 最新版本与安装包：见 [Releases](https://github.com/FishXIN/VaultGuard/releases)
- 版本变更记录：见 [CHANGELOG.md](./CHANGELOG.md)
- 问题反馈与需求建议：见 [Issues](https://github.com/FishXIN/VaultGuard/issues)

当前采用较规范的 GitHub 发布治理：

- 使用语义化版本号：`v主版本.次版本.修订版本`
- Release Notes 按类别组织：新增、修复、UI、打包、文档
- Issue / PR 使用标签治理，便于筛选功能、缺陷、优先级和发布归属
- 默认只在明确发布时创建新版本，不把日常源码同步误当成 Release

## 核心特性

- **文件安全第一**：原子写入（临时文件 + 校验 + 重命名）、覆盖前不破坏旧文件、完整性校验、失败隔离、断电安全清理、默认绝不删除目标文件。
- **增量优先**：只处理新增/更新的文件，已备份未变更文件绝不重复拷贝；复制后回写源 mtime 保证下次对比准确。
- **先选后执行**：对比完成后展示清单（新增/更新/跳过 + 预计传输），用户确认后才执行。
- **可中断·可续传**：任务可暂停/中断，断点持久化到 SQLite，下次可「从断点继续」或「重新开始」。
- **可追溯**：每次任务与每个文件操作写入 SQLite，并输出可读文本日志。

## 首次打开（绕过系统安全提示）

本应用未购买 Apple / Windows 付费代码签名证书，因此从网上下载后，系统会在**首次打开**时弹出安全提示。这是正常的来源校验机制，按下列步骤放行**一次**即可，之后永久不再提示。

### macOS

> 双击若提示「无法打开，因为 Apple 无法检查其是否包含恶意软件」：

- 方式 A（推荐）：在「备份了嘛.app」上**右键 → 打开**，在弹窗中再次点击「打开」。
- 方式 B：打开「系统设置 → 隐私与安全性」，下滑找到被拦截的提示，点击「仍要打开」。
- 方式 C（命令行一键去除隔离标记）：

```bash
xattr -dr com.apple.quarantine "/Applications/备份了嘛.app"
```

> 若提示「应用已损坏，应移到废纸篓」，同样执行上面的 `xattr` 命令即可恢复。

### Windows

> 双击若出现蓝色「Windows 已保护你的电脑 (SmartScreen)」窗口：

- 点击窗口中的「更多信息」→ 出现「仍要运行」按钮 → 点击即可运行。

## 快速开始

### 方式一：双击启动（macOS）

双击 `启动VaultGuard.command`，首次运行会自动创建虚拟环境并安装依赖。

### 方式二：命令行

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 图形界面
.venv/bin/python main.py

# 命令行（核心逻辑）
.venv/bin/python cli.py compare <源目录> <目标目录>        # 只对比，打印清单
.venv/bin/python cli.py backup  <源目录> <目标目录>        # 对比并执行（会询问确认）
.venv/bin/python cli.py backup  <源目录> <目标目录> -y     # 跳过确认
.venv/bin/python cli.py backup  <源目录> <目标目录> --resume  # 从断点继续
.venv/bin/python cli.py history                            # 查看历史任务
```

## 项目结构

```
VaultGuard/
├── main.py                  # 图形界面入口
├── cli.py                   # 命令行入口
├── build_app.sh             # 构建 macOS 桌面应用（dist/VaultGuard.app）
├── requirements.txt
├── vaultguard/
│   ├── core/                # 核心逻辑
│   │   ├── models.py        # 数据模型
│   │   ├── config.py        # 设置与数据目录
│   │   ├── scanner.py       # 模块1：扫描与对比引擎
│   │   ├── executor.py      # 模块2+3：原子复制 + 断点续传
│   │   ├── database.py      # 模块4：SQLite 日志/任务持久化
│   │   └── service.py       # 服务层（编排 CLI/GUI 共用）
│   └── ui/                  # 模块5+6：VaultGuard 桌面图形界面
│       ├── app.py
│       └── helpers.py
└── tests/
    └── test_core.py         # 核心逻辑自动化测试
```

## 数据位置

配置、SQLite 数据库与文本日志存储于平台标准目录：

- macOS：`~/Library/Application Support/VaultGuard`
- Windows：`%APPDATA%\VaultGuard`

可通过环境变量 `VAULTGUARD_DATA_DIR` 覆盖。

## 运行测试

```bash
PYTHONPATH=. .venv/bin/python tests/test_core.py
```

覆盖：原子复制、mtime 回写、增量跳过、更新检测、失败隔离、断点续传、排除规则。

## 设置项

mtime 容差、是否对比大小、hash 完整性校验、删除策略（默认关闭）、排除规则、单文件重试次数。

## 尚未包含

- 打包签名与公证（模块5的安装包）：需 Apple Developer ID / Windows 代码签名证书，请另行提供。
- 定时自动备份、多备份配置、删除同步回收区（模块6可选增强）。
