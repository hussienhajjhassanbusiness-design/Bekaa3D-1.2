import { test, expect } from "@playwright/test";

// FVS001-T16 action 4 — the ONE spec in this entire suite allowed to
// require a real, running local VS-001 backend. Deliberately excluded from
// the default "smoke" project (see playwright.config.ts's per-project
// testMatch) and invoked only via its own `npm run test:e2e:backend`
// script — never by `npm run test:e2e`, never by `npm test`, never by
// `npm run build`.
//
// This spec exists specifically to prove genuine connectivity through the
// real stack: browser/test request -> frontend /api/health/ready (same
// origin) -> next.config.ts's rewrite -> the actual backend's
// GET /health/ready. It must NOT mock, intercept, or fulfill this route
// itself (page.route/request interception would defeat the entire point),
// and it must NOT assert any response-body field — the health body shape
// is intentionally unconfirmed (bekaa3d-api-contract); only the HTTP-level
// outcome is meaningful here.
test("GET /api/health/ready reaches the real backend through the frontend proxy", async ({ request }) => {
  const response = await request.get("/api/health/ready");

  expect(response.ok()).toBe(true);
});
