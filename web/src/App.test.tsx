import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { ApprovalPanel } from "./components/ApprovalPanel";
import { Timeline } from "./components/Timeline";

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 201,
    headers: { "Content-Type": "application/json" },
  });
}

describe("App", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts a mock task and shows the selected task id", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        id: "task-1",
        status: "running",
        workspace: "/repo",
        goal: "inspect",
        mode: "supervised",
        provider: "mock",
        pending_approvals: [],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await user.clear(screen.getByLabelText(/workspace/i));
    await user.type(screen.getByLabelText(/workspace/i), "/repo");
    await user.type(screen.getByLabelText(/goal/i), "inspect");
    await user.click(screen.getByRole("button", { name: /start task/i }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tasks",
      expect.objectContaining({ method: "POST" }),
    );
    expect(await screen.findByText("task-1")).toBeInTheDocument();
  });

  it("shows a validation error for malformed mock decision JSON", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText(/goal/i), "inspect");
    await user.clear(screen.getByLabelText(/mock decisions/i));
    await user.type(screen.getByLabelText(/mock decisions/i), "{{}");
    await user.click(screen.getByRole("button", { name: /start task/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/json array/i);
  });

  it("submits task-scoped approval and disables duplicate decisions", async () => {
    const user = userEvent.setup();
    const onDecision = vi.fn(() => new Promise<void>(() => {}));
    render(
      <ApprovalPanel
        approvals={[{ id: "approval-1", task_id: "task-1", reason: "shell", status: "pending" }]}
        onDecision={onDecision}
      />,
    );

    await user.click(screen.getByRole("button", { name: /allow for task/i }));

    expect(onDecision).toHaveBeenCalledWith("approval-1", true, "task");
    expect(screen.getByRole("button", { name: /allow once/i })).toBeDisabled();
  });

  it("renders timeline events in sequence order", () => {
    render(
      <Timeline
        connection="realtime"
        events={[
          { sequence: 2, type: "task_completed", payload: {}, created_at: "2026-08-11T00:00:02Z" },
          { sequence: 1, type: "task_started", payload: {}, created_at: "2026-08-11T00:00:01Z" },
        ]}
      />,
    );

    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      expect.stringContaining("task_started"),
      expect.stringContaining("task_completed"),
    ]);
  });

  it("loads an initial task and posts cancellation", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "task-1", status: "running", workspace: "/repo", goal: "inspect", mode: "supervised", provider: "mock", pending_approvals: [] })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "task-1", status: "cancelled", workspace: "/repo", goal: "inspect", mode: "supervised", provider: "mock", pending_approvals: [] })));
    vi.stubGlobal("fetch", fetchMock);

    render(<App initialTaskId="task-1" />);
    expect(await screen.findByText("running")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /cancel task/i }));

    expect(fetchMock).toHaveBeenCalledWith("/api/tasks/task-1/cancel", expect.objectContaining({ method: "POST" }));
  });

  it("explains that restart recovery reruns from the beginning", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "task-1",
        status: "needs_review",
        workspace: "/repo",
        goal: "inspect",
        mode: "supervised",
        provider: "mock",
        pending_approvals: [],
        recovery_required: true,
        recovery_reason: "服务重启后需人工复核",
        resumable: true,
      })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "task-1",
        status: "needs_review",
        report: "需要人工复核",
      })));
    vi.stubGlobal("fetch", fetchMock);

    render(<App initialTaskId="task-1" />);

    expect(await screen.findByText("服务重启后需人工复核")).toBeInTheDocument();
    expect(screen.getByText("从头重新执行")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /resume safely/i })).toBeEnabled();
  });

  it("does not show resume action for manual needs review tasks", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "task-1",
        status: "needs_review",
        workspace: "/repo",
        goal: "inspect",
        mode: "supervised",
        provider: "mock",
        pending_approvals: [],
        recovery_required: false,
        recovery_reason: null,
        resumable: false,
      })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "task-1",
        status: "needs_review",
        report: "需要人工复核",
      })));
    vi.stubGlobal("fetch", fetchMock);

    render(<App initialTaskId="task-1" />);

    expect(await screen.findByText("needs_review")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /resume safely/i })).not.toBeInTheDocument();
  });
});
