import { describe, it, expect } from "vitest";
import { beginSetDefault, rollbackSetDefault, settleSetDefault } from "./addressDefaultOptimistic";
import type { AddressModel } from "./addressModel";

// Phase 5B — the real AddressModel fields; only id/displayLines/isDefault
// matter to these tests.
const ADDRESS_BASE: Omit<AddressModel, "id" | "displayLines" | "isDefault"> = {
  label: "Home",
  recipientName: "Jane Doe",
  phone: "+9613123456",
  governorate: "beirut",
  city: "Beirut",
  area: null,
  street: null,
  landmarkNotes: "Blue gate",
};

// FVS-023-IMPLEMENTATION-PLAN.md T03 — a pure, contract-independent
// optimistic-state helper. No endpoint, body, or status code is
// invented here; this only models the three lifecycle transitions
// VS-019's own "server-authoritative, never locally flip two toggles
// and assume final" rule requires. A real mutation (T07, blocked on
// the backend contract) wires these to an actual PATCH/refetch later.

const ADDRESSES: readonly AddressModel[] = [
  { ...ADDRESS_BASE, id: "addr-1", displayLines: ["Jane Doe"], isDefault: true },
  { ...ADDRESS_BASE, id: "addr-2", displayLines: ["John Doe"], isDefault: false },
  { ...ADDRESS_BASE, id: "addr-3", displayLines: ["Alex Doe"], isDefault: false },
];

describe("beginSetDefault", () => {
  it("flips exactly one address to isDefault true — the requested id — and all others false", () => {
    const result = beginSetDefault(ADDRESSES, "addr-2");
    expect(result.addresses.filter((a) => a.isDefault)).toHaveLength(1);
    expect(result.addresses.find((a) => a.id === "addr-2")?.isDefault).toBe(true);
    expect(result.addresses.find((a) => a.id === "addr-1")?.isDefault).toBe(false);
  });

  it("sets pendingId to the requested id", () => {
    const result = beginSetDefault(ADDRESSES, "addr-2");
    expect(result.pendingId).toBe("addr-2");
  });

  it("never mutates the input array", () => {
    const original = ADDRESSES.map((a) => ({ ...a }));
    beginSetDefault(ADDRESSES, "addr-2");
    expect(ADDRESSES).toEqual(original);
  });
});

describe("rollbackSetDefault", () => {
  it("restores the exact previous snapshot and clears pendingId", () => {
    const result = rollbackSetDefault(ADDRESSES);
    expect(result.addresses).toEqual(ADDRESSES);
    expect(result.pendingId).toBeNull();
  });
});

describe("settleSetDefault", () => {
  it("adopts the authoritative array verbatim, even when it differs from the optimistic guess", () => {
    // Server truth disagrees with the client's optimistic guess (e.g. a
    // concurrent change elsewhere made addr-3 the real default) — the
    // UI must end up matching the server, never the local guess.
    const authoritative: readonly AddressModel[] = [
      { ...ADDRESS_BASE, id: "addr-1", displayLines: ["Jane Doe"], isDefault: false },
      { ...ADDRESS_BASE, id: "addr-2", displayLines: ["John Doe"], isDefault: false },
      { ...ADDRESS_BASE, id: "addr-3", displayLines: ["Alex Doe"], isDefault: true },
    ];
    const result = settleSetDefault(authoritative);
    expect(result.addresses).toEqual(authoritative);
    expect(result.pendingId).toBeNull();
  });
});
