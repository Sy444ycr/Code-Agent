import type { TaskDetail } from "../types";

interface TaskSummaryProps { task: TaskDetail; canResume?: boolean; onCancel: () => Promise<void>; onResume: () => Promise<void>; }

export function TaskSummary({ task, canResume = false, onCancel, onResume }: TaskSummaryProps) {
  const active = ["pending", "running", "waiting_approval"].includes(task.status);
  return <section aria-label="task summary"><h2>{task.id}</h2><p>{task.status}</p><p>{task.goal}</p>{active && <button onClick={() => void onCancel()}>Cancel task</button>}{canResume && <button onClick={() => void onResume()}>Resume safely</button>}</section>;
}
