# Task 24：WebUI 打包与干净安装验收设计

## 1. 目标与范围

Task 24 使 `code-agent web` 在从 wheel 或 sdist 安装后的干净环境中，稳定提供已构建的 WebUI 和既有 API。任务只处理 WebUI 发布产物、Python 包资源、安装验收和 CI 顺序；不改变任务生命周期、Provider、SQLite 协议、TUI 或 WebUI 交互功能。

本任务不实现 Docker 镜像、远程部署、多用户服务、CDN、运行时前端编译或 Python 构建时隐式安装 Node.js。

## 2. 发布边界

前端和 Python 包构建保持两个明确阶段：

```text
npm ci -> npm run test -- --run -> npm run build
  -> 发布暂存目录中的包内 Web 资源
  -> python -m build
  -> wheel / sdist
  -> 干净虚拟环境安装 wheel
  -> code-agent web
```

- Node/Vite 只负责生成 WebUI 资源；`python -m build` 不调用 Node、npm 或 Vite。
- 发布脚本在 Python 打包前检查前端产物存在且完整，并将它们复制到受 Python 包配置管理的暂存路径。
- 打包构建只包含该暂存路径，不直接依赖被 Git 忽略的 `web/dist`。
- 若未执行前端构建或产物缺失，发布预检以明确中文错误失败；不得生成没有 WebUI 的发布包。
- 本地开发可继续从仓库 `web/dist` 提供资源；已安装包优先从 `code_agent/web_dist` 提供资源。

## 3. 资源与路由契约

运行时资源解析顺序固定为：

1. 已安装包中的 `code_agent/web_dist`；
2. 源码工作区的 `web/dist`；
3. 两者均不存在时，不挂载静态资源，仅保留 FastAPI API。

静态资源路由只在 API 路由定义之后注册，因此：

- `/api/...` 始终由 API 处理，不能回退到 `index.html`；
- `/` 返回 WebUI 的 `index.html`；
- 已存在的 JS、CSS 和其他资源按文件返回；
- 未匹配的非 API 路径回退至 `index.html`，支持前端路由；
- 所有请求路径须解析并限制在资源根目录内，路径穿越只能回退到入口页，不能读取包外文件。

## 4. 安装与验收

干净安装验收使用临时虚拟环境，安装刚构建的 wheel，不复用开发环境的 editable 安装。验收必须验证：

- `code-agent --help` 与 `code-agent web --help` 可运行；
- 安装后的 Python 包能定位包内 `web_dist/index.html`；
- 启动本地 `code-agent web` 后，`GET /` 返回 WebUI；
- 静态资源可获取，前端路由回退正确；
- `GET /api/tasks/not-found` 返回 API 的 `404`，不被静态资源路由接管；
- 包构建和验收不读取 Provider 密钥、不访问真实 Provider 网络。

默认端口仍为 `127.0.0.1:8000`。测试使用临时端口并确保服务进程在结束后退出。

## 5. CI 与文档

GitHub Actions 与 GitLab CI 都以相同的发布顺序运行：安装 Node 依赖、前端测试与构建、发布预检、Python 测试/静态检查、Python 打包、wheel 安装验收。CI 不执行真实 Provider E2E。

README 说明本地开发和发布构建的差异：开发 `code-agent web` 可使用 `web/dist`，发布包必须先完成前端构建和发布暂存。AGENT_LOG 与 SPEC_PROCESS 使用中文记录红绿测试、构建命令、干净安装结果和任何环境限制。

## 6. 错误处理与安全

- 静态资源缺失不暴露本机绝对路径，只以固定中文诊断提示发布者。
- 资源服务不接受外部路径或配置字段；所有解析仅使用包内或仓库内的既定目录。
- 打包和安装验收输出不记录 Provider 凭据、HTTP Authorization、真实 Provider 响应正文或用户任务内容。
- 不修改既有 workspace 边界、Policy Engine、审批状态机和 API/SSE 事件格式。

## 7. 验收门槛

实施按严格 TDD 进行：先为发布预检、资源解析、静态/API 路由优先级和干净安装写失败测试；再写最小实现；最后运行 Python pytest、Ruff、Mypy、WebUI Vitest/Vite build、Python build 和 wheel 安装验收。任何跳过、警告或环境限制均如实记录。
