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

## 复审修复

### RED

复审后，测试改为自行运行 `npm ci` 和 `npm run build`，并使用 `python -m build --outdir`
写入专用目录以避免复用 `dist/` 中的旧 wheel；同时新增静态资源、SPA 回退和
`web_assets --check` 输出断言。执行测试得到 `1 failed, 2 passed`，失败断言为
`assets_check.stdout == "Web assets available\\n"`，实际输出为空，证明模块入口尚未实现
`--check` 合约。

### GREEN

在 `code_agent.web_assets` 中新增最小 CLI 入口：`--check` 仅检查 `static_dist_path()`，
成功时输出 `Web assets available`，缺失时输出不含凭据的错误信息并返回 1。测试辅助同时：

- 依据操作系统选择 `npm`/`npm.cmd`、venv 的 `bin`/`Scripts` 和 console entry 后缀；
- 将子进程输出固定为 UTF-8 替换解码，消除 Windows 编码警告；
- 从 `index.html` 提取实际 `/assets/...` 路径并断言 200，验证客户端路由 SPA 回退为根页面。

GREEN 验证：`tests/integration/test_package_install.py -q` 为 `3 passed in 98.53s`。

## 第二轮复审修复

### RED

新增安装隔离要求：所有已安装 wheel 的 CLI 与服务命令都必须以 `tmp_path` 为工作目录，
并移除 `PYTHONPATH` 与 `PYTHONHOME`；API 请求改为真实应用路由
`/api/tasks/not-found`。旧测试会在源码目录执行 CLI，且仅检查由静态路由拒绝的 `/api`，
因此不能证明上述两个约束。

### GREEN

测试在安装 wheel 后创建一个伪造的 `code_agent` 包并设置父进程 `PYTHONPATH` 指向它；
验收辅助在启动 `web_assets --check`、两个 `code-agent --help` 命令和 Web 服务前复制环境后
移除该变量及 `PYTHONHOME`，并始终使用 `tmp_path` 作为工作目录。这样任一子进程若继承
源码/父进程路径都会导入伪造包并失败。HTTP 验收现在请求
`/api/tasks/not-found`，由真实的应用路由返回 404。

GREEN 验证：`tests/integration/test_package_install.py -q` 为 `3 passed in 94.27s`。
