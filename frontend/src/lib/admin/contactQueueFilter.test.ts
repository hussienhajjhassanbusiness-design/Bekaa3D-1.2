import { describe, it, expect } from "vitest";
import { normalizeContactStatusFilter } from "./contactQueueFilter";

// FVS-017-IMPLEMENTATION-PLAN.md T04 — URL-state helper, deliberately
// key-agnostic: no governing document gives a literal `?status=`
// example for /admin/contact-messages (unlike /shop's own confirmed
// category=/material=/colour= keys), so the exact URL parameter NAME
// stays an open, explicitly recorded decision (plan §0) — this
// function only normalizes whatever raw string value a caller already
// extracted (regardless of which key it came from), never reading
// URLSearchParams itself and never choosing the key name.

describe("normalizeContactStatusFilter", () => {
  it("normalizes a missing value to the default (all)", () => {
    expect(normalizeContactStatusFilter(null)).toBe("all");
  });

  it("round-trips each known normalized status", () => {
    expect(normalizeContactStatusFilter("new")).toBe("new");
    expect(normalizeContactStatusFilter("read")).toBe("read");
    expect(normalizeContactStatusFilter("replied")).toBe("replied");
    expect(normalizeContactStatusFilter("archived")).toBe("archived");
  });

  it("round-trips the explicit all value", () => {
    expect(normalizeContactStatusFilter("all")).toBe("all");
  });

  it("normalizes an unknown/garbage value to the default (all), never passing it through raw", () => {
    expect(normalizeContactStatusFilter("deleted")).toBe("all");
    expect(normalizeContactStatusFilter("<script>")).toBe("all");
  });

  it("normalizes an empty string to the default", () => {
    expect(normalizeContactStatusFilter("")).toBe("all");
  });
});
