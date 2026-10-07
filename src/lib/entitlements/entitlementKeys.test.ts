import { describe, it, expect } from "vitest";
import { entitlementKeys } from "./entitlementKeys";

// FVS-020-IMPLEMENTATION-PLAN.md T01 — the ONE canonical entitlement
// query-key family. FVS-019's manual grant (and any future payment-
// driven grant/revocation) MUST invalidate `entitlementKeys.root`
// rather than inventing a parallel `libraryQueryKey`/
// `ownedProductsQueryKey` for the same server resource
// (#ARCHITECTURE-CANONICAL-ENTITLEMENTS-QUERY). No page/cursor
// argument is baked into `list()` — /me/entitlements' pagination
// status is unconfirmed (plan §1), so only a stable, parameterless key
// is built now.

describe("entitlementKeys", () => {
  it("has a stable root key", () => {
    expect(entitlementKeys.root).toEqual(["entitlements"]);
  });

  it("derives the list key from the canonical root", () => {
    expect(entitlementKeys.list()).toEqual(["entitlements", "list"]);
  });

  it("derives the detail key from the canonical root, keyed by the exact entitlement id", () => {
    expect(entitlementKeys.detail("ent-1")).toEqual(["entitlements", "detail", "ent-1"]);
    expect(entitlementKeys.detail("ent-2")).toEqual(["entitlements", "detail", "ent-2"]);
  });

  it("keeps list and detail keys distinguishable from each other and from the bare root", () => {
    const list = entitlementKeys.list();
    const detail = entitlementKeys.detail("ent-1");
    const root = entitlementKeys.root;
    expect(list).not.toEqual(detail);
    expect(list).not.toEqual(root);
    expect(detail).not.toEqual(root);
  });

  it("takes no page/cursor argument for list() — pagination is unconfirmed, not baked in", () => {
    // @ts-expect-error — list() intentionally accepts no arguments
    expect(() => entitlementKeys.list(1)).not.toThrow();
  });
});
