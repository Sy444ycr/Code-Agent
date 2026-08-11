import type { TaskCreateInput, TaskDetail } from "./types";

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
