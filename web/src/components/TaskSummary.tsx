import type { TaskDetail } from "../types";

interface TaskSummaryProps { task: TaskDetail; canResume?: boolean; onCancel: () => Promise<void>; onResume: () => Promise<void>; }

export function TaskSummary({ task, canResume = false, onCancel, onResume }: TaskSummaryProps) {
  const active = ["pending", "running", "waiting_approval"].includes(task.status);
  const recoveryReason = task.recovery_required ? (task.recovery_reason ?? "服务重启后需人工复核") : null;
  return <section aria-label="task summary"><h2>{task.id}</h2><p>{task.status}</p><p>{task.goal}</p><p>Provider: {task.provider}</p>{recoveryReason && <p>{recoveryReason}</p>}{recoveryReason && <p>{ "从头重新执行" }</p>}{task.report && <p>{task.report}</p>}{active && <button onClick={() => void onCancel()}>Cancel task</button>}{canResume && <button onClick={() => void onResume()}>Resume safely</button>}</section>;
}
