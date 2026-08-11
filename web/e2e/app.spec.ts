import { expect, test } from "@playwright/test";

const task = { id: "task-1", status: "waiting_approval", workspace: "/repo", goal: "inspect", mode: "supervised", provider: "mock", pending_approvals: [{ id: "approval-1", task_id: "task-1", reason: "shell", status: "pending" }] };

test("creates a mock task and exposes approval controls", async ({ page }) => { await page.route("**/api/tasks", (route) => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(task) })); await page.route("**/api/tasks/task-1", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(task) })); await page.goto("/"); await page.getByLabel(/goal/i).fill("inspect"); await page.getByRole("button", { name: /start task/i }).click(); await expect(page.getByRole("button", { name: /allow once/i })).toBeVisible(); });
test("keeps creation controls inside a 390px viewport", async ({ page }) => { await page.setViewportSize({ width: 390, height: 844 }); await page.goto("/"); await expect(page.getByRole("button", { name: /start task/i })).toBeVisible(); expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true); });
