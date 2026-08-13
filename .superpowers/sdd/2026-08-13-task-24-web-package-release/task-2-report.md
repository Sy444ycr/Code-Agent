# Task 2 执行报告：包内资源解析与 SPA/API 路由契约

## 实现内容

- 新增 `_asset_candidates()`，按 `src/code_agent/web_dist`、`web/dist` 的顺序提供候选目录。
- `static_dist_path()` 仅接受包含 `index.html` 的目录，确保无完整前端资源时保持纯 API 行为。
- 静态文件处理改用 `Path.is_relative_to()` 验证解析后的请求路径在静态目录内，避免字符串前缀判定导致的路径边界问题。
- `create_app()` 原有的 `mount_web_assets(app)` 已位于全部 `/api` 路由声明之后，符合 API 优先于 SPA 回退的契约，因此未作无效修改。
- 增加集成测试，验证包内资源优先、SPA 回退，以及未知 API 路由仍返回 404。

## TDD 记录

1. RED：新增包内资源优先与 API 路由优先测试。首次执行目标命令时，worktree 内没有 `.venv`；改用共享虚拟环境解释器后，测试因缺少 `_asset_candidates` 而失败（1 failed, 2 passed）。
2. GREEN：以最小实现新增候选目录函数，改为检查 `index.html`，并使用 `is_relative_to()` 完成路径边界检查。
3. GREEN 验证：`tests/integration/test_web_runtime.py` 通过（3 passed）。

## 最终验证

执行以下命令并全部成功：

```powershell
$env:PYTHONPATH='src'; & 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe' -m pytest tests/integration/test_web_runtime.py tests/integration/test_api_sse.py -q
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\ruff.exe' check src tests/integration/test_web_runtime.py
& 'C:\Users\sy444\Desktop\Agents\.venv\Scripts\mypy.exe' src
```

结果：11 个测试通过；Ruff 无问题；mypy 在 33 个源文件中无问题。测试输出含既有 FastAPI/TestClient 弃用警告，未由本任务引入。
