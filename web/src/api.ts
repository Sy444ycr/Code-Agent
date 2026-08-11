import type { TaskCreateInput, TaskDetail, TaskEvent } from "./types";

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const body: unknown = await response.json();

  if (!response.ok) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : "请求失败";
    throw new Error(detail);
  }

  return body as T;
}

export function createTask(input: TaskCreateInput): Promise<TaskDetail> {
  return requestJson<TaskDetail>("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getTask(id: string): Promise<TaskDetail> { return requestJson<TaskDetail>(`/api/tasks/${id}`, {}); }
export function cancelTask(id: string): Promise<TaskDetail> { return requestJson<TaskDetail>(`/api/tasks/${id}/cancel`, { method: "POST" }); }
export function resumeTask(id: string): Promise<TaskDetail> { return requestJson<TaskDetail>(`/api/tasks/${id}/resume`, { method: "POST" }); }
export function decideApproval(id: string, approved: boolean, scope: "once" | "task"): Promise<unknown> { return requestJson(`/api/approvals/${id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved, scope, actor: "web-user" }) }); }

export function connectTaskEvents(id: string, after: number, onEvent: (event: TaskEvent) => void, onError: () => void): () => void {
  if (typeof EventSource === "undefined") return () => undefined;
  const source = new EventSource(`/api/tasks/${id}/events/stream?after=${after}`);
  ["message", "task_started", "approval_requested", "approval_decided", "task_completed"].forEach((type) => source.addEventListener(type, (event) => onEvent(JSON.parse((event as MessageEvent).data) as TaskEvent)));
  source.onerror = onError;
  return () => source.close();
}
