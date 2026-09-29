import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

// @testing-library/react's own automatic afterEach(cleanup) registration
// relies on a *global* `afterEach` existing (e.g. via Vitest's `globals:
// true`). This project deliberately does not enable that (see
// vitest.config.mts — kept off to avoid an unrequested tsconfig change for
// "vitest/globals" types), so cleanup must be wired explicitly here instead
// — otherwise every component test after the first in a file renders into
// an already-populated document and queries collide across tests.
afterEach(() => {
  cleanup();
});
