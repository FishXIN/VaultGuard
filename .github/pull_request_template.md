## 变更摘要

- 解决了什么问题：
- 用户可见的变化：
- 影响的平台或模块：

## 验证

- [ ] `PYTHONPATH=. .venv/bin/python tests/test_core.py`
- [ ] `.venv/bin/python -m compileall -q vaultguard tests`
- [ ] `git diff --check`
- [ ] 已在受影响平台手动验证
- [ ] 涉及文件操作时，已验证中断、失败和断点续传

## 数据安全

- [ ] 不会覆盖或删除无关文件
- [ ] 保留 `.bak.tmp` + 校验 + 原子替换约束
- [ ] 数据库状态只在文件安全完成后提交
- [ ] 不涉及文件读写逻辑

## 发布说明

- [ ] 需要更新 `CHANGELOG.md`
- [ ] 需要刷新 macOS / Windows Release 资产
- [ ] 不影响发布

## 截图或日志

如涉及 UI、异常处理或性能变化，请附上必要证据，并移除敏感路径与文件内容。
