// The one origin the Playwright suite runs against (playwright.config.ts
// starts the server here). Deliberately NOT :3000, so a full E2E run never
// collides with — or silently reuses — a developer's own `npm run dev`.
// Specs that need an absolute URL (cookie scope, mocked payment
// redirect_url, exact toHaveURL) import it instead of hard-coding a port.
export const E2E_PORT = 3100;
export const E2E_ORIGIN = `http://localhost:${E2E_PORT}`;
