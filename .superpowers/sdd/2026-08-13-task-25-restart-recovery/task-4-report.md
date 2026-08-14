# Task 4 实施报告

## 范围

- 修改 `src/code_agent/tui/screens.py`
- 修改 `tests/integration/test_tui.py`
- 修改 `web/src/types.ts`
- 修改 `web/src/components/TaskSummary.tsx`
- 修改 `web/src/App.tsx`
- 修改 `web/src/App.test.tsx`

## TDD 过程

### 先写失败测试

先在客户端测试中补充以下行为：

- TUI 在 `needs_review + recovery_required=true + resumable=true` 时显示中文恢复提示：
  - `服务重启后需人工复核`
  - `从头重新执行`
- TUI 仅对 restart recovery 任务响应恢复快捷键，不再把普通 `cancelled` 结果误判为可恢复
- WebUI 消费 `recovery_required`、`recovery_reason`、`resumable`
- WebUI 仅在 `resumable === true` 时显示恢复按钮
- WebUI 对普通 `needs_review` 任务不显示恢复按钮

### 红灯验证

先运行指定测试验证失败：

- `web/src/App.test.tsx` 新增用例先失败，失败原因为前端尚未渲染恢复提示，也未按 `resumable` 控制恢复按钮
- worktree 内没有 `.\.venv\Scripts\python.exe`，因此改用仓库根目录虚拟环境执行同一份 `tests/integration/test_tui.py`，用于完成 TDD 红灯/绿灯验证

### 最小实现

1. TUI 结果屏新增恢复摘要与“从头重新执行”提示
2. TUI 恢复动作改为仅在 `status == needs_review && resumable == true` 时可触发
3. Web `TaskDetail` 类型补充恢复字段
4. Web `TaskSummary` 渲染恢复原因与“从头重新执行”提示
5. Web `App` 将恢复按钮严格绑定到 `task.resumable === true`

### 保持不变的行为

- 原有审批屏与审批提交流程未改动
- TUI/Web 原有错误通知行为保持不变；恢复失败时仍只通知、不切换当前界面
- 未把任意 `needs_review` 一概视为可恢复

## 验证结果

```text
$env:PYTHONPATH="src"; & "C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe" -m pytest tests/integration/test_tui.py -q
27 passed in 7.30s
```

```text
npm.cmd test -- --run
Test Files  2 passed (2)
Tests  8 passed (8)
```

```text
npm.cmd run build
tsc -b && vite build
✓ built in 260ms
```

## 结果总结

- TUI 与 WebUI 现在都能显示“服务重启后需人工复核”和“从头重新执行”
- 恢复入口现在只对真正 restart-recoverable 的任务开放
- 普通 `needs_review`、原有错误提示、审批行为都保持原语义

## Concerns

- brief 指定的 Python 测试命令使用 `.\.venv\Scripts\python.exe`，但当前隔离 worktree 不包含该虚拟环境；本次验证使用仓库根目录的 `C:\Users\sy444\Desktop\Agents\.venv\Scripts\python.exe` 完成
- `npm test` 与 `npm run build` 仍会输出既有 Vite `configLoader: 'native'` 预告警告；不影响本次任务通过，且不在 brief 范围内
