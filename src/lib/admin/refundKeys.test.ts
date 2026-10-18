import { describe, it, expect } from "vitest";
import { refundKeys } from "./refundKeys";

// FVS-032-IMPLEMENTATION-PLAN.md T01 — the ONE canonical refund
// query-key family, mirroring the same canonical pattern used
// elsewhere in this app
// (#ARCHITECTURE-CANONICAL-REFUNDS-QUERY). No page/cursor argument on
// list() — the real refund-list pagination shape is unconfirmed.

describe("refundKeys", () => {
  it("has a stable root key", () => {
    expect(refundKeys.root).toEqual(["refunds"]);
  });

  it("derives the list key from the canonical root", () => {
    expect(refundKeys.list()).toEqual(["refunds", "list"]);
  });

  it("derives the detail key from the canonical root, keyed by the exact refund id", () => {
    expect(refundKeys.detail("refund-1")).toEqual(["refunds", "detail", "refund-1"]);
    expect(refundKeys.detail("refund-2")).toEqual(["refunds", "detail", "refund-2"]);
  });

  it("keeps list and detail keys distinguishable from each other and from the bare root", () => {
    const list = refundKeys.list();
    const detail = refundKeys.detail("refund-1");
    const root = refundKeys.root;
    expect(list).not.toEqual(detail);
    expect(list).not.toEqual(root);
    expect(detail).not.toEqual(root);
  });

  it("takes no page/cursor argument for list() — pagination is unconfirmed, not baked in", () => {
    // @ts-expect-error — list() intentionally accepts no arguments
    expect(() => refundKeys.list(1)).not.toThrow();
  });
});
