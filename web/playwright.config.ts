import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://127.0.0.1:5173" },
  projects: [{ name: "Microsoft Edge", use: { ...devices["Desktop Edge"], channel: "msedge" } }],
  webServer: { command: "npm.cmd run dev -- --host 127.0.0.1", url: "http://127.0.0.1:5173", reuseExistingServer: true },
});
