import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests_js/**/*.test.js"],
    environment: "node",
  },
});
