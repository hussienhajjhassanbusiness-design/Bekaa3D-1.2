import { describe, it, expect } from "vitest";
import { parseShopUrlState, buildShopUrlParams } from "./shopUrlState";

// FVS-013-IMPLEMENTATION-PLAN.md T01 — pure browser-URL-state helpers
// for /shop. This is NOT the backend query adapter: the backend's exact
// facet/sort/cursor parameter names are still NEEDS BACKEND CONFIRMATION
// (plan §1) — only the literal `q`/`category`/`material`/`colour`/
// `sort`/`cursor` keys confirmed by FRONTEND-VERTICAL-SLICE-PLAN.md's
// own routing line are handled.
//
// FVS-013 FOLLOW-UP (facet cardinality correction): facets are modeled
// as `readonly string[]` — zero, one, or many — because the backend has
// not confirmed whether a facet permits one or multiple selected
// values. Writing more than one value per facet is an explicit,
// deliberate gate (#BACKEND-GATE-FACET-SERIALIZATION): no repeated-
// param/comma/pipe/JSON encoding is guessed.
//
// Cursor is always treated as opaque — never parsed/decoded. Changing
// any filter/sort/search dimension clears the cursor: a cursor token is
// only valid for the specific query that produced it, so carrying it
// into a different query is simply incorrect, not a style choice.

describe("parseShopUrlState", () => {
  it("defaults every facet to an empty array, sort/cursor to null, and q to an empty string when the URL is empty", () => {
    expect(parseShopUrlState(new URLSearchParams())).toEqual({
      category: [],
      material: [],
      colour: [],
      sort: null,
      q: "",
      cursor: null,
    });
  });

  it("round-trips q", () => {
    expect(parseShopUrlState(new URLSearchParams("q=printer")).q).toBe("printer");
  });

  it("round-trips sort", () => {
    expect(parseShopUrlState(new URLSearchParams("sort=relevance")).sort).toBe("relevance");
  });

  it("treats cursor as an opaque string, never decoding it", () => {
    const state = parseShopUrlState(new URLSearchParams("cursor=eyJvcGFxdWUiOnRydWV9"));
    expect(state.cursor).toBe("eyJvcGFxdWUiOnRydWV9");
  });

  it("treats an empty facet value as absent (empty array), not an empty-string filter", () => {
    expect(parseShopUrlState(new URLSearchParams("category=")).category).toEqual([]);
  });

  it("reads a single facet value into a one-element array", () => {
    expect(parseShopUrlState(new URLSearchParams("category=printers")).category).toEqual(["printers"]);
  });

  it("reads multiple same-named facet params into a multi-element array (model is cardinality-neutral)", () => {
    const state = parseShopUrlState(new URLSearchParams("category=printers&category=accessories"));
    expect(state.category).toEqual(["printers", "accessories"]);
  });

  it("decodes URL-encoded values correctly", () => {
    expect(parseShopUrlState(new URLSearchParams("q=3d%20printer")).q).toBe("3d printer");
  });
});

describe("buildShopUrlParams", () => {
  it("preserves unrelated existing params when updating q", () => {
    const current = new URLSearchParams("utm_source=newsletter");
    const next = buildShopUrlParams(current, { q: "printer" });
    expect(next.get("q")).toBe("printer");
    expect(next.get("utm_source")).toBe("newsletter");
  });

  it("removes a facet param when set back to an empty array", () => {
    const current = new URLSearchParams("category=printers");
    const next = buildShopUrlParams(current, { category: [] });
    expect(next.has("category")).toBe(false);
  });

  it("writes a single-element facet array using the one confirmed encoding", () => {
    const current = new URLSearchParams();
    const next = buildShopUrlParams(current, { category: ["printers"] });
    expect(next.get("category")).toBe("printers");
  });

  it("refuses to guess an encoding for a multi-value facet update, instead of silently choosing one", () => {
    const current = new URLSearchParams();
    expect(() => buildShopUrlParams(current, { category: ["printers", "accessories"] })).toThrow(
      /NEEDS BACKEND CONFIRMATION/
    );
  });

  it("clears the cursor when category changes", () => {
    const current = new URLSearchParams("cursor=abc123&category=old");
    const next = buildShopUrlParams(current, { category: ["new"] });
    expect(next.has("cursor")).toBe(false);
    expect(next.get("category")).toBe("new");
  });

  it("clears the cursor when q changes", () => {
    const current = new URLSearchParams("cursor=abc123&q=old");
    const next = buildShopUrlParams(current, { q: "new" });
    expect(next.has("cursor")).toBe(false);
  });

  it("clears the cursor when sort changes", () => {
    const current = new URLSearchParams("cursor=abc123&sort=relevance");
    const next = buildShopUrlParams(current, { sort: "newest" });
    expect(next.has("cursor")).toBe(false);
  });

  it("does not clear the cursor when only the cursor itself is being set (pagination)", () => {
    const current = new URLSearchParams("category=printers");
    const next = buildShopUrlParams(current, { cursor: "next-token" });
    expect(next.get("cursor")).toBe("next-token");
    expect(next.get("category")).toBe("printers");
  });

  it("round-trips through parse after a build", () => {
    const next = buildShopUrlParams(new URLSearchParams(), { q: "stand", sort: "newest", category: ["printers"] });
    expect(parseShopUrlState(next)).toEqual({
      category: ["printers"],
      material: [],
      colour: [],
      sort: "newest",
      q: "stand",
      cursor: null,
    });
  });
});
