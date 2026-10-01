# 参与贡献

感谢你改进 VaultGuard。这个项目直接处理用户文件，因此正确性、可恢复性和跨平台一致性优先于功能数量。

## 开始之前

1. 搜索现有 Issue 和 Pull Request。
2. Bug 修复请先提供可复现步骤。
3. 较大的功能建议先创建 Issue，明确交互、异常路径和数据安全约束。
4. 安全漏洞按 [SECURITY.md](SECURITY.md) 私密报告。

## 开发环境

要求 Python 3.12。

```bash
git clone https://github.com/FishXIN/VaultGuard.git
cd VaultGuard

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install "flet==0.86.5"
```

Windows PowerShell 请使用 `.\.venv\Scripts\python.exe` 和 `.\.venv\Scripts\pip.exe`。

## 分支与提交

分支名应描述意图：

- `feat/scheduled-backup`
- `fix/windows-path-layout`
- `docs/security-policy`

提交信息遵循 Conventional Commits：

- `feat:` 新功能
- `fix:` Bug 修复
- `perf:` 性能优化
- `docs:` 文档
- `test:` 测试
- `build:` 构建
- `ci:` 自动化
- `refactor:` 不改变行为的重构
- `chore:` 维护

一个 Pull Request 只解决一类问题，不要混入无关重构或格式化。

## 文件安全约束

涉及核心备份逻辑时必须保持：

- 写入目标文件前使用同目录临时文件。
- 校验完成后才允许原子替换。
- 失败文件不得标记为完成。
- 暂停、取消、崩溃后可以仅重试未完成文件。
- 删除同步默认关闭，坏盘抢救模式不得删除目标文件。
- 磁盘健康检查不得运行自检、修复、扇区扫描或写入测速。
- 同一任务不得并发执行。

如果修改了这些约束，请在 PR 中说明失败路径、恢复策略和验证证据。

## 验证

提交前至少运行：

```bash
PYTHONPATH=. .venv/bin/python tests/test_core.py
.venv/bin/python -m compileall -q vaultguard tests
git diff --check
```

根据改动范围补充：

- UI 改动：macOS / Windows 截图和最小窗口检查。
- 文件复制：原子性、取消、失败隔离、断点续传测试。
- 数据库：迁移兼容性与中断恢复测试。
- 发布：macOS 和 Windows 安装包及 SHA-256 校验。

## Pull Request

PR 应包含：

- 问题与改动摘要
- 用户可见变化
- 风险和回滚方式
- 测试命令与结果
- UI 截图或关键日志（如适用）
- `CHANGELOG.md` 更新（如有用户可见变化）

## 发布规则

- 版本号遵循 SemVer：`vMAJOR.MINOR.PATCH`
- 稳定 Release 必须同时包含 macOS、Windows 和 `checksums.txt`
- 日常提交不创建 Release
- 预发布仅用于明确的测试版本

参与本项目即表示同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
