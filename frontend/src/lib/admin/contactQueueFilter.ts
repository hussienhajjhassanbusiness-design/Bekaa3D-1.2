import type { ContactMessageStatus } from "./contactMessageWorkflow";

export type ContactStatusFilter = "all" | ContactMessageStatus;

const VALID_FILTERS: readonly string[] = ["all", "new", "read", "replied", "archived"];

// #ARCHITECTURE-CONTACT-QUEUE-URL-STATE
//
// Deliberately key-agnostic: unlike /shop's confirmed `category=`/
// `material=`/`colour=` keys (FVS-013), no governing document gives a
// literal URL-parameter-name example for /admin/contact-messages'
// status filter (FRONTEND-VERTICAL-SLICE-PLAN.md only says "URL-synced
// status filter" conceptually). Choosing a parameter name now would be
// a silent, unconfirmed production decision
// (FVS-017-IMPLEMENTATION-PLAN.md §1/§4) — so this function takes an
// already-extracted raw string (regardless of which key a future route
// reads it from) and only normalizes its VALUE. An unknown/garbage/
// empty/missing value always resolves to the safe default ("all")
// rather than being passed through raw.
export function normalizeContactStatusFilter(rawValue: string | null): ContactStatusFilter {
  if (rawValue !== null && VALID_FILTERS.includes(rawValue)) {
    return rawValue as ContactStatusFilter;
  }
  return "all";
}
