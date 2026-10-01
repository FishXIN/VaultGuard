# Security Policy

VaultGuard 会直接读取源目录并写入目标目录。任何可能导致文件损坏、误删、路径越界或任意代码执行的问题都应按安全问题处理。

## Supported Versions

| Version | Supported |
| --- | :---: |
| Latest stable release | ✅ |
| Older releases | ❌ |

请先在 [Releases](https://github.com/FishXIN/VaultGuard/releases/latest) 确认最新稳定版本。

## Reporting a Vulnerability

请不要在公开 Issue 中披露尚未修复的漏洞细节。

优先使用 GitHub 仓库的 **Security → Report a vulnerability** 私密报告入口。如果该入口不可用，请联系仓库维护者，并提供：

- 受影响版本与操作系统
- 可复现的最小步骤
- 预期行为与实际行为
- 可能受影响的数据范围
- 日志、堆栈或演示文件
- 建议的修复方案（可选）

维护者会尽快确认报告。修复发布前，请避免公开利用细节或真实用户数据。

## Security Boundaries

- VaultGuard 不会主动上传备份内容到云端。
- 磁盘健康检查仅查询系统元数据，不运行自检、修复、扇区扫描或写入测速。
- 删除同步默认关闭；启用后应先使用可恢复的数据验证。
- 下载的未签名安装包可能触发系统安全提示，请始终从本仓库 Releases 下载并校验 SHA-256。
