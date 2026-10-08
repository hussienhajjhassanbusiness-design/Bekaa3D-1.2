import { describe, it, expect } from "vitest";
import type { OrderActionAffordance } from "./orderActionModel";

// FVS-031-IMPLEMENTATION-PLAN.md §1 — the neutral, domain-free
// server-provided-affordance shape, extracted so both customer
// cancellation and admin transitions (FVS-030) consume the same
// primitive rather than two parallel ones
// (#ARCHITECTURE-SERVER-PROVIDED-ORDER-ACTIONS).

describe("OrderActionAffordance", () => {
  it("has exactly id, label, requiresConfirmation — no backend-specific fields", () => {
    const affordance: OrderActionAffordance = { id: "cancel", label: "Cancel this item", requiresConfirmation: true };
    expect(affordance).toEqual({ id: "cancel", label: "Cancel this item", requiresConfirmation: true });
  });
});
