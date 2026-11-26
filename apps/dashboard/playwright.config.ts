import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  timeout: 90000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:3000",
    headless: true,
    viewport: { width: 1440, height: 1050 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: process.env.AG_CHROME_PATH
      ? { executablePath: process.env.AG_CHROME_PATH }
      : {},
  },
  reporter: [["list"], ["html", { open: "never" }]],
});
