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
    // FVS001-T16: e2e/*.spec.ts are Playwright specs, run only via
    // `npm run test:e2e`/`test:e2e:backend` — never by Vitest. Vitest's
    // default include glob also matches `*.spec.ts`, so without this
    // exclusion it tries to execute Playwright's test.describe()/test()
    // API through its own runner and fails outright. Vitest's own default
    // excludes (node_modules, dist, .git, etc.) are repeated here since
    // setting `exclude` replaces them rather than extending them.
    exclude: [
      "**/node_modules/**",
      "**/dist/**",
      "**/.{idea,git,cache,output,temp}/**",
      "**/{karma,rollup,webpack,vite,vitest,jest,ava,babel,nyc,cypress,tsup,build}.config.*",
      "e2e/**",
    ],
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
});
