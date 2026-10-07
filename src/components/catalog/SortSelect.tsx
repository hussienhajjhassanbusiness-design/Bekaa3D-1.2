"use client";

import { useId } from "react";

export interface SortOption {
  value: string;
  label: string;
}

export interface SortSelectProps {
  options: readonly SortOption[];
  value: string | null;
  onChange: (next: string) => void;
  label?: string;
}

// #FVS013-SORT-ALLOWLIST
//
// Data-driven ONLY — this component never embeds a guessed sort value
// (e.g. "most-downloaded", "price-low") internally. VS-013 confirms
// sort is allowlisted/backend-restricted but gives no exhaustive value
// list (FVS-013-IMPLEMENTATION-PLAN.md §1); the caller supplies whatever
// the real, confirmed allowlist turns out to be. An empty `options`
// array disables the control rather than rendering a guessed default.
export function SortSelect({ options, value, onChange, label = "Sort by" }: SortSelectProps) {
  const selectId = useId();

  return (
    <div>
      <label htmlFor={selectId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
        {label}
      </label>
      <select
        id={selectId}
        value={value ?? ""}
        disabled={options.length === 0}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 rounded-sm border border-border-default px-3 py-2 text-body text-text-primary"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
