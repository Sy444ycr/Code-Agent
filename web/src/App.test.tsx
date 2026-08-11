import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

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
});
