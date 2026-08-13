import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "./App";

describe("provider selection", () => {
  it("sends a non-mock provider without mock decisions", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "task-1", status: "running", workspace: ".", goal: "inspect", mode: "supervised", provider: "openai", pending_approvals: [] }), { status: 201 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await user.type(screen.getByLabelText(/goal/i), "inspect");
    await user.selectOptions(screen.getByLabelText(/provider/i), "openai");
    await user.click(screen.getByRole("button", { name: /start task/i }));

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.provider).toBe("openai");
    expect(body).not.toHaveProperty("mock_decisions");
  });
});
