import { useState, type FormEvent } from "react";

import { createTask } from "../api";
import type { PermissionMode, TaskDetail } from "../types";

interface TaskFormProps {
  onCreated: (task: TaskDetail) => void;
}

export function TaskForm({ onCreated }: TaskFormProps) {
  const [workspace, setWorkspace] = useState(".");
  const [goal, setGoal] = useState("");
  const [mode, setMode] = useState<PermissionMode>("supervised");
  const [mockDecisions, setMockDecisions] = useState("[]");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!goal.trim()) {
      setError("Goal is required");
      return;
    }

    let decisions: unknown;
    try {
      decisions = JSON.parse(mockDecisions);
    } catch {
      setError("Mock decisions must be a JSON array");
      return;
    }
    if (!Array.isArray(decisions)) {
      setError("Mock decisions must be a JSON array");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const task = await createTask({
        workspace,
        goal: goal.trim(),
        mode,
        provider: "mock",
        mock_decisions: decisions,
        acceptance_checks: [],
      });
      onCreated(task);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "请求失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <label>
        Workspace
        <input aria-label="workspace" value={workspace} onChange={(event) => setWorkspace(event.target.value)} />
      </label>
      <label>
        Goal
        <input aria-label="goal" value={goal} onChange={(event) => setGoal(event.target.value)} />
      </label>
      <label>
        Mode
        <select aria-label="mode" value={mode} onChange={(event) => setMode(event.target.value as PermissionMode)}>
          <option value="plan">plan</option>
          <option value="supervised">supervised</option>
          <option value="auto">auto</option>
        </select>
      </label>
      <label>
        Mock decisions
        <textarea aria-label="mock decisions" value={mockDecisions} onChange={(event) => setMockDecisions(event.target.value)} />
      </label>
      <button disabled={submitting} type="submit">{submitting ? "Creating…" : "Start Task"}</button>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}
