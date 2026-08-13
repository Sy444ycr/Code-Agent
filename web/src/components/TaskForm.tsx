import { useState, type FormEvent } from "react";

import { createTask } from "../api";
import type { PermissionMode, TaskCreateInput, TaskDetail } from "../types";

interface TaskFormProps {
  onCreated: (task: TaskDetail) => void;
}

export function TaskForm({ onCreated }: TaskFormProps) {
  const [workspace, setWorkspace] = useState(".");
  const [goal, setGoal] = useState("");
  const [mode, setMode] = useState<PermissionMode>("supervised");
  const [provider, setProvider] = useState("mock");
  const [mockDecisions, setMockDecisions] = useState("[]");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!goal.trim()) {
      setError("Goal is required");
      return;
    }

    let decisions: unknown[] | undefined;
    if (provider === "mock") {
      try {
        const parsed: unknown = JSON.parse(mockDecisions);
        if (!Array.isArray(parsed)) throw new Error("invalid");
        decisions = parsed;
      } catch {
        setError("Mock decisions must be a JSON array");
        return;
      }
    }

    setSubmitting(true);
    setError("");
    try {
      const input: TaskCreateInput = {
        workspace,
        goal: goal.trim(),
        mode,
        provider,
        acceptance_checks: [],
      };
      if (decisions) input.mock_decisions = decisions;
      const task = await createTask(input);
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
        Provider
        <select aria-label="provider" value={provider} onChange={(event) => setProvider(event.target.value)}>
          <option value="mock">mock</option>
          <option value="openai">openai</option>
        </select>
      </label>
      <label>
        Mock decisions
        <textarea aria-label="mock decisions" disabled={provider !== "mock"} value={mockDecisions} onChange={(event) => setMockDecisions(event.target.value)} />
      </label>
      <button disabled={submitting} type="submit">{submitting ? "Creating…" : "Start Task"}</button>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}
