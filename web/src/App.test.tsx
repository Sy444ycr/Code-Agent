import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders task console controls", () => {
    render(<App />);
    expect(screen.getByLabelText(/workspace/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/goal/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start task/i })).toBeInTheDocument();
  });
  it("shows validation when goal is empty", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /start task/i }));
    expect(screen.getByText(/goal is required/i)).toBeInTheDocument();
  });
});
