"use client";

import { useId } from "react";

export interface DefaultAddressOption {
  id: string;
  label: string;
  isDefault: boolean;
}

export interface DefaultAddressSelectorProps {
  options: readonly DefaultAddressOption[];
  onSelect: (addressId: string) => void;
  // A switch currently in flight (real mutation is T07, blocked on the
  // backend contract) — disables every option without removing any
  // option's accessible label.
  pendingId?: string | null;
}

// #FVS023-DEFAULT-ADDRESS-SELECTOR
//
// A real radio group — never independent checkboxes/switches, since
// only one address can ever be the default (VS-019's own rule). Named
// DefaultAddressSelector rather than the plan's literal
// "SetDefaultToggle" wording, which would wrongly imply toggle/
// checkbox semantics: accessibility wins over the component name.
//
// Setting default is server-authoritative (VS-019's Logic line) — this
// component only reports intent via `onSelect`; it never locally
// decides the switch succeeded. A real mutation (blocked on the
// backend contract, plan §6) wires this to
// `beginSetDefault`/`rollbackSetDefault`/`settleSetDefault`
// (`addressDefaultOptimistic.ts`) once it exists.
export function DefaultAddressSelector({ options, onSelect, pendingId = null }: DefaultAddressSelectorProps) {
  const statusId = useId();
  // Unique per instance so multiple selectors rendered on the same
  // page never collide into one native radio group.
  const groupName = useId();
  const isPending = pendingId !== null;

  return (
    <fieldset aria-busy={isPending || undefined} aria-describedby={isPending ? statusId : undefined}>
      <legend className="font-label text-label-caps uppercase leading-4 text-on-surface">Default address</legend>
      {isPending && (
        <p id={statusId} role="status" className="mt-1 text-xs text-on-surface-variant">
          Updating default address…
        </p>
      )}
      <div className="mt-2 flex flex-col gap-2">
        {options.map((option) => (
          <label key={option.id} className="flex items-center gap-2 text-sm text-on-surface">
            <input
              type="radio"
              name={groupName}
              value={option.id}
              checked={option.isDefault}
              disabled={isPending}
              onChange={() => onSelect(option.id)}
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
