"use client";

import { Button } from "@/components/forms/Button";

export interface FacetOption {
  value: string;
  label: string;
  checked: boolean;
  disabled?: boolean;
}

export interface FacetGroup {
  id: string;
  legend: string;
  options: readonly FacetOption[];
}

export interface AppliedFilter {
  groupId: string;
  value: string;
  label: string;
}

export interface FilterPanelProps {
  groups: readonly FacetGroup[];
  onChange: (groupId: string, value: string, checked: boolean) => void;
  appliedFilters?: readonly AppliedFilter[];
  onRemoveFilter?: (groupId: string, value: string) => void;
  onClearAll?: () => void;
}

// #FVS013-CATALOGUE-FILTERS
//
// Generic, presentational facet panel — carries zero hardcoded facet
// entries. Category/material/colour groups are always supplied by the
// caller (the real live category/material/colour lists, once FVS-010's
// own public endpoints are confirmed and wired — not yet, see
// FVS-013-IMPLEMENTATION-PLAN.md §1). No fetch, no persistence. Colour
// facets render the same plain text labels as every other group — this
// component has no swatch concept of its own; a caller that wants a
// swatch supplies one via `label`/a richer option shape later, but
// text remains the only thing this component ever relies on.
export function FilterPanel({ groups, onChange, appliedFilters = [], onRemoveFilter, onClearAll }: FilterPanelProps) {
  return (
    <div>
      {appliedFilters.length > 0 && (
        <div className="mb-4">
          <ul className="flex flex-wrap gap-2">
            {appliedFilters.map((filter) => (
              <li key={`${filter.groupId}:${filter.value}`}>
                <button
                  type="button"
                  aria-label={`Remove ${filter.label} filter`}
                  onClick={() => onRemoveFilter?.(filter.groupId, filter.value)}
                  className="rounded-pill border border-border-default px-3 py-1 text-caption text-text-primary"
                >
                  {filter.label} ✕
                </button>
              </li>
            ))}
          </ul>
          {onClearAll && (
            <Button type="button" onClick={onClearAll} className="mt-2">
              Clear filters
            </Button>
          )}
        </div>
      )}

      {groups.map((group) => (
        <fieldset key={group.id} className="mb-4">
          <legend className="text-label font-semibold uppercase tracking-label text-text-primary">
            {group.legend}
          </legend>
          {group.options.length === 0 ? (
            <p className="mt-2 text-caption text-text-secondary">No options available.</p>
          ) : (
            <div className="mt-2 flex flex-col gap-2">
              {group.options.map((option) => (
                <label key={option.value} className="flex items-center gap-2 text-body text-text-primary">
                  <input
                    type="checkbox"
                    checked={option.checked}
                    disabled={option.disabled}
                    onChange={(event) => onChange(group.id, option.value, event.target.checked)}
                  />
                  {option.label}
                </label>
              ))}
            </div>
          )}
        </fieldset>
      ))}
    </div>
  );
}
