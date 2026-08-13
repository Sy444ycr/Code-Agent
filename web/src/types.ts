export type PermissionMode = "plan" | "supervised" | "auto";

export type TaskStatus =
  | "pending"
  | "running"
  | "waiting_approval"
  | "succeeded"
  | "needs_review"
  | "blocked"
  | "failed"
  | "budget_exhausted"
  | "cancelled";

export interface Approval {
  id: string;
  task_id: string;
  reason: string;
  status: string;
}

export interface TaskDetail {
  id: string;
  status: TaskStatus;
  workspace: string;
  goal: string;
  mode: PermissionMode;
  provider: string;
  pending_approvals: Approval[];
  report?: string;
  changed_files?: string[];
  verification?: unknown[];
}

export interface TaskCreateInput {
  workspace: string;
  goal: string;
  mode: PermissionMode;
  provider: string;
  mock_decisions?: unknown[];
  acceptance_checks: string[];
}

export interface TaskEvent {
  sequence: number;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export type ConnectionState = "connecting" | "realtime" | "reconnecting" | "ended" | "failed";
