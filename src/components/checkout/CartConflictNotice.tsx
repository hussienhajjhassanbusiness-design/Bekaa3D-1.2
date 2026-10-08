import type { CartConflictLine } from "@/lib/checkout/checkoutModels";

export interface CartConflictNoticeProps {
  lines: readonly CartConflictLine[];
}

// #FVS026 — renders each line's own caller-supplied message
// individually, never collapsed into a generic "Checkout failed."
// `kind` is used only for a per-line visual grouping, never to
// fabricate text of its own.
export function CartConflictNotice({ lines }: CartConflictNoticeProps) {
  if (lines.length === 0) {
    return null;
  }

  return (
    <ul role="alert" className="flex flex-col gap-2">
      {lines.map((line) => (
        <li key={line.lineId} className="rounded-md border border-warning bg-warning-bg p-3 text-body text-text-primary">
          {line.message}
        </li>
      ))}
    </ul>
  );
}
