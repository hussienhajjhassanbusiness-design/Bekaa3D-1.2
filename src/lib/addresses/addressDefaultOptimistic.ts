import type { AddressModel } from "./addressModel";

export interface AddressDefaultOptimisticState {
  addresses: readonly AddressModel[];
  pendingId: string | null;
}

// Pure, contract-independent optimistic-state helper
// (FVS-023-IMPLEMENTATION-PLAN.md §5). No endpoint, request body, or
// status code is invented here — this only models the lifecycle
// VS-019's own "server-authoritative, never locally flip two toggles
// and assume final" rule requires. Phase 5B: the mounted address book
// does NOT use these — it shows a pending state and then refetches the
// server's list after PUT /me/addresses/{id}/default (useAddresses.ts),
// which is simpler and never shows a guessed default.

// Begin an optimistic default switch: exactly one address becomes the
// default locally, immediately, while the request is in flight.
export function beginSetDefault(current: readonly AddressModel[], nextDefaultId: string): AddressDefaultOptimisticState {
  return {
    addresses: current.map((address) => ({ ...address, isDefault: address.id === nextDefaultId })),
    pendingId: nextDefaultId,
  };
}

// The request failed: restore the exact pre-optimistic snapshot.
export function rollbackSetDefault(previousSnapshot: readonly AddressModel[]): AddressDefaultOptimisticState {
  return { addresses: previousSnapshot, pendingId: null };
}

// The request settled successfully: adopt whatever the server actually
// returned, verbatim — never the local optimistic guess. This is the
// server-truth reconciliation step VS-019 requires.
export function settleSetDefault(authoritative: readonly AddressModel[]): AddressDefaultOptimisticState {
  return { addresses: authoritative, pendingId: null };
}
