import { describe, it, expect } from "vitest";
import { parseAdminListUrlState, buildAdminListUrlParams } from "./adminListUrlState";

// FVS-009-IMPLEMENTATION-PLAN.md T03 — pure browser-URL-state helpers
// only. This is NOT the backend query-adapter: the backend's own
// search/page parameter names are still NEEDS BACKEND CONFIRMATION (plan
// §1), so these helpers only ever read/write the browser's own `q`/`page`
// convention (FRONTEND-VERTICAL-SLICE-PLAN.md's own State line).
//
// Deliberately does NOT reset page to 1 when q changes — nothing in the
// governing plans confirms that as required behavior at the helper level
// (plan §5); a caller that wants it must pass `page: 1` explicitly.

describe("parseAdminListUrlState", () => {
  it("defaults q to an empty string when absent", () => {
    expect(parseAdminListUrlState(new URLSearchParams())).toEqual({ q: "", page: 1 });
  });

  it("reads q from the search params", () => {
    expect(parseAdminListUrlState(new URLSearchParams("q=alice"))).toEqual({ q: "alice", page: 1 });
  });

  it("defaults page to 1 when absent", () => {
    expect(parseAdminListUrlState(new URLSearchParams("q=alice"))).toEqual({ q: "alice", page: 1 });
  });

  it("reads a valid page number", () => {
    expect(parseAdminListUrlState(new URLSearchParams("page=3"))).toEqual({ q: "", page: 3 });
  });

  it("resolves a non-numeric page to 1", () => {
    expect(parseAdminListUrlState(new URLSearchParams("page=abc"))).toEqual({ q: "", page: 1 });
  });

  it("resolves a zero page to 1", () => {
    expect(parseAdminListUrlState(new URLSearchParams("page=0"))).toEqual({ q: "", page: 1 });
  });

  it("resolves a negative page to 1", () => {
    expect(parseAdminListUrlState(new URLSearchParams("page=-5"))).toEqual({ q: "", page: 1 });
  });

  it("resolves a fractional page to 1", () => {
    expect(parseAdminListUrlState(new URLSearchParams("page=2.5"))).toEqual({ q: "", page: 1 });
  });
});

describe("buildAdminListUrlParams", () => {
  it("sets q while preserving unrelated existing params", () => {
    const current = new URLSearchParams("tab=details");
    const next = buildAdminListUrlParams(current, { q: "bob" });
    expect(next.get("q")).toBe("bob");
    expect(next.get("tab")).toBe("details");
  });

  it("omits the q param entirely when set back to empty", () => {
    const current = new URLSearchParams("q=bob");
    const next = buildAdminListUrlParams(current, { q: "" });
    expect(next.has("q")).toBe(false);
  });

  it("sets page while leaving q untouched", () => {
    const current = new URLSearchParams("q=bob");
    const next = buildAdminListUrlParams(current, { page: 2 });
    expect(next.get("page")).toBe("2");
    expect(next.get("q")).toBe("bob");
  });

  it("omits the page param when set back to 1 (default)", () => {
    const current = new URLSearchParams("page=4");
    const next = buildAdminListUrlParams(current, { page: 1 });
    expect(next.has("page")).toBe(false);
  });

  it("does not touch page when only q is updated", () => {
    const current = new URLSearchParams("page=3");
    const next = buildAdminListUrlParams(current, { q: "new search" });
    expect(next.get("page")).toBe("3");
  });

  it("round-trips through parse after a build", () => {
    const current = new URLSearchParams();
    const next = buildAdminListUrlParams(current, { q: "carol", page: 2 });
    expect(parseAdminListUrlState(next)).toEqual({ q: "carol", page: 2 });
  });
});
