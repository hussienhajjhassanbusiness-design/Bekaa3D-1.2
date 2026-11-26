import { describe, it, expect } from "vitest";
import { addressKeys } from "./addressKeys";

// FVS-023-IMPLEMENTATION-PLAN.md T01 — the ONE canonical address
// query-key family (#ARCHITECTURE-CANONICAL-ADDRESSES-QUERY). FVS-026
// checkout MUST reuse/invalidate this key rather than inventing a
// checkout-local address cache. `list()` takes no page/cursor
// argument — /me/addresses' pagination status is unconfirmed (plan
// §1). Keys carry resource/id only, never address content
// (#SECURITY-CUSTOMER-ADDRESS).

describe("addressKeys", () => {
  it("has a stable root key", () => {
    expect(addressKeys.root).toEqual(["addresses"]);
  });

  it("derives the list key from the canonical root", () => {
    expect(addressKeys.list()).toEqual(["addresses", "list"]);
  });

  it("derives the detail key from the canonical root, keyed by the exact address id", () => {
    expect(addressKeys.detail("addr-1")).toEqual(["addresses", "detail", "addr-1"]);
    expect(addressKeys.detail("addr-2")).toEqual(["addresses", "detail", "addr-2"]);
  });

  it("keeps list and detail keys distinguishable from each other and from the bare root", () => {
    const list = addressKeys.list();
    const detail = addressKeys.detail("addr-1");
    const root = addressKeys.root;
    expect(list).not.toEqual(detail);
    expect(list).not.toEqual(root);
    expect(detail).not.toEqual(root);
  });

  it("takes no page/cursor argument for list() — pagination is unconfirmed, not baked in", () => {
    // @ts-expect-error — list() intentionally accepts no arguments
    expect(() => addressKeys.list(1)).not.toThrow();
  });

  it("never embeds address content (name/phone/street/etc.) in the detail key — id only", () => {
    const key = addressKeys.detail("addr-1");
    expect(key).toHaveLength(3);
    expect(key[2]).toBe("addr-1");
  });
});
