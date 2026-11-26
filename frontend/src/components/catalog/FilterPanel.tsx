"use client";

import { Icon } from "@/components/ui/Icon";

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
//
// Batch 3 — Stitch shop filter sidebar (COMPONENT-SPECS §19): mono caps
// group legends, 20px primary checkboxes with Inter labels, applied
// filters as removable tags (§18) and "Clear filters" as a text action.
// The same instance is rendered in the desktop aside and in the tablet /
// mobile drawer, with the same handlers.
export function FilterPanel({ groups, onChange, appliedFilters = [], onRemoveFilter, onClearAll }: FilterPanelProps) {
  return (
    <div className="flex flex-col gap-8">
      {appliedFilters.length > 0 && (
        <div className="flex flex-col items-start gap-3">
          <ul className="flex flex-wrap gap-2">
            {appliedFilters.map((filter) => (
              <li key={`${filter.groupId}:${filter.value}`}>
                <button
                  type="button"
                  aria-label={`Remove ${filter.label} filter`}
                  onClick={() => onRemoveFilter?.(filter.groupId, filter.value)}
                  className="inline-flex min-h-8 items-center gap-1.5 rounded-badge bg-primary/10 py-1 pl-2.5 pr-1.5 font-body text-sm font-medium text-primary transition-colors duration-200 hover:bg-primary/20"
                >
                  {filter.label}
                  <Icon name="close" className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
          {onClearAll && (
            <button
              type="button"
              onClick={onClearAll}
              className="inline-flex min-h-8 items-center rounded-badge font-label text-label-caps uppercase text-primary underline-offset-4 hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>
      )}

      {groups.map((group) => (
        <fieldset key={group.id}>
          <legend className="mb-4 font-label text-label-caps uppercase text-on-surface-variant">{group.legend}</legend>
          {group.options.length === 0 ? (
            <p className="font-body text-sm text-on-surface-variant">No options available.</p>
          ) : (
            <div className="flex flex-col gap-1">
              {group.options.map((option) => (
                <label
                  key={option.value}
                  className="group flex min-h-9 cursor-pointer items-center gap-3 font-body text-body-md text-on-surface-variant hover:text-on-surface has-[:checked]:font-semibold has-[:checked]:text-on-surface has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50"
                >
                  <input
                    type="checkbox"
                    checked={option.checked}
                    disabled={option.disabled}
                    onChange={(event) => onChange(group.id, option.value, event.target.checked)}
                    className="h-5 w-5 shrink-0 cursor-pointer rounded-badge accent-primary"
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
