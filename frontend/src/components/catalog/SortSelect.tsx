"use client";

import { useId } from "react";
import { Icon } from "@/components/ui/Icon";

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

  // Batch 3 — Stitch results-toolbar sort (COMPONENT-SPECS §20): mono
  // "SORT BY" label beside a tinted, borderless native select with a
  // decorative chevron. Still a native <select> with its own label.
  return (
    <div className="flex items-center gap-3">
      <label htmlFor={selectId} className="shrink-0 font-label text-label-caps uppercase text-on-surface-variant">
        {label}
      </label>
      <div className="relative">
        <select
          id={selectId}
          value={value ?? ""}
          disabled={options.length === 0}
          onChange={(event) => onChange(event.target.value)}
          className="min-h-11 w-full appearance-none rounded-control bg-surface-container py-2 pl-4 pr-10 font-body text-body-md text-on-surface disabled:cursor-not-allowed disabled:opacity-50"
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <Icon
          name="chevron-down"
          className="pointer-events-none absolute right-3 top-1/2 h-5 w-5 -translate-y-1/2 text-on-surface-variant"
        />
      </div>
    </div>
  );
}
