import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.mts"],
    // FVS001-T02 has zero permanent tests by design (the proof test that
    // verified this config was deleted per the plan). Without this, Vitest
    // exits 1 on an empty suite, which would break `npm run test` until
    // FVS001-T04 adds the first real test. Real tests arriving later exit
    // this "empty suite" path automatically — this is not a way to silence
    // a suite that has tests but is failing.
    passWithNoTests: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
});
