import { useEffect, useState } from "react";

import { cancelTask, connectTaskEvents, decideApproval, getTask, resumeTask } from "./api";
import { ApprovalPanel } from "./components/ApprovalPanel";
import { TaskForm } from "./components/TaskForm";
import { TaskSummary } from "./components/TaskSummary";
import { Timeline } from "./components/Timeline";
import type { ConnectionState, TaskDetail, TaskEvent } from "./types";

interface AppProps { initialTaskId?: string; }

export default function App({ initialTaskId }: AppProps) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [taskId, setTaskId] = useState(initialTaskId);
  const [error, setError] = useState("");
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("connecting");

  useEffect(() => { if (taskId) void getTask(taskId).then(setTask).catch((caught) => setError(caught.message)); }, [taskId]);
  useEffect(() => {
    if (!taskId) return;
    let cursor = 0; let retry: ReturnType<typeof setTimeout> | undefined;
    const close = connectTaskEvents(taskId, cursor, (event) => { if (event.sequence <= cursor) return; cursor = event.sequence; setEvents((current) => [...current, event]); setConnection(event.type === "task_completed" ? "ended" : "realtime"); }, () => { setConnection("reconnecting"); retry = setTimeout(() => setConnection("connecting"), 500); });
    return () => { close(); if (retry) clearTimeout(retry); };
  }, [taskId]);
  async function refresh(action: () => Promise<TaskDetail>) { try { setTask(await action()); } catch (caught) { setError(caught instanceof Error ? caught.message : "请求失败"); } }

  return (
    <main>
      <h1>Code-Agent Task Console</h1>
      <TaskForm onCreated={(created) => { setTask(created); setTaskId(created.id); }} />
      {error && <p role="alert">{error}</p>}
      {task && <><TaskSummary task={task} onCancel={() => refresh(() => cancelTask(task.id))} onResume={() => refresh(() => resumeTask(task.id))} /><ApprovalPanel approvals={task.pending_approvals} onDecision={async (id, approved, scope) => { await decideApproval(id, approved, scope); setTask(await getTask(task.id)); }} /><Timeline connection={connection} events={events} /></>}
      {!task && <section aria-label="timeline">No active task</section>}
    </main>
  );
}
