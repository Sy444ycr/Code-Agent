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
});
