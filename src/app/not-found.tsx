import { NotFoundContent } from "@/components/feedback/NotFoundContent";

// Next.js App Router's global catch-all 404 — handles every unmatched URL.
// Content extracted into NotFoundContent (FVS-029-IMPLEMENTATION-PLAN.md
// T06): a second real reuse case now exists — OrderDetail's foreign/
// nonexistent-order case renders the exact same component, so there is
// only one visible not-found experience, not two independently-
// maintained copies. The AppLayout/Header/Footer shell is owned by the
// root layout (FVS001-T14) — this file owns only its own not-found
// content.
export default function NotFound() {
  return <NotFoundContent />;
}
