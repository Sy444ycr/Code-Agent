# Task 3 执行报告：wheel 干净安装与 HTTP 验收

## 修改范围

- `tests/integration/test_package_install.py`

新增真实发布工件验收：先暂存 WebUI、构建 wheel，并断言其中存在
`code_agent/web_dist/index.html`；随后在临时虚拟环境安装 wheel，验证资源检查命令、
`code-agent --help` 与 `code-agent web --help`。测试以已安装的 `code-agent web`
启动本地服务，轮询根路径，并验证 `/` 返回 WebUI、`/api` 返回 404。服务进程在
`finally` 中终止，超时则强制结束；测试未读取或调用任何 Provider 凭据。

## TDD 记录

### RED

新增验收测试后执行：

```powershell
$env:PYTHONPATH="src;."; C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe -m pytest tests/integration/test_package_install.py -q
```

结果：`1 failed, 2 passed`。失败原因符合预期：`prepare_web_package()` 报告
`web/dist/index.html` 缺失，说明测试确实依赖可发布的前端构建产物。

### GREEN

构建前端后首次运行暴露清洁虚拟环境缺少 wheel 运行依赖（`fastapi`）；将安装方式从
`pip install --no-deps` 调整为普通 `pip install <wheel>`，以验证真实用户安装体验。

随后再次执行同一集成测试，结果为：`3 passed in 76.07s`。

## 验证

- `npm.cmd ci`：成功。
- `npm.cmd test -- --run`：`2 passed`、`6 passed`。
- `npm.cmd run build`：成功生成 `web/dist`。
- `ruff check tests/integration/test_package_install.py`：通过。
- `git diff --check`：通过。
- 完整发布链：`prepare_web_package.py`、集成测试（`3 passed in 77.36s`）和
  `python -m build` 均以退出码 0 完成。
