import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/benchmark",
  timeout: 22 * 60_000,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:4173", trace: "retain-on-failure" },
  webServer: {
    command:
      "pnpm build && pnpm exec vite preview --host 127.0.0.1 --port 4173",
    port: 4173,
    reuseExistingServer: false
  }
});
