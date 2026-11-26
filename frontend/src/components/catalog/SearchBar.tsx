"use client";

import { useId, type FormEvent } from "react";
import { Icon } from "@/components/ui/Icon";

export interface SearchSuggestion {
  label: string;
  // Optional, caller-confirmed destination — this component never
  // fabricates a route. Absent means selection is callback-only.
  href?: string;
}

export interface SearchBarProps {
  value: string;
  onChange: (next: string) => void;
  onSubmit?: (value: string) => void;
  suggestions?: readonly SearchSuggestion[];
  isLoadingSuggestions?: boolean;
  onSelectSuggestion?: (suggestion: SearchSuggestion) => void;
  label?: string;
  // Keeps the label for assistive tech but hides it visually, for a field
  // whose purpose is already obvious from its surroundings (the shop hero).
  hideLabel?: boolean;
}

// #FVS013-SEARCH-BAR
//
// Presentational only — never calls the suggestions endpoint itself,
// never chooses a production debounce interval or minimum character
// count (both NEEDS BACKEND/PRODUCT CONFIRMATION,
// FVS-013-IMPLEMENTATION-PLAN.md §1). `onChange` fires on every
// keystroke; a future caller wires its own debounce once the real
// suggestions contract is confirmed — inventing one here would encode
// an unconfirmed product decision into shared UI.
//
// Suggestions render as plain text (never dangerouslySetInnerHTML) and
// as real buttons — simpler and fully keyboard-operable without
// building a full ARIA combobox/listbox interaction model that no
// governing evidence actually requires yet.
export function SearchBar({
  value,
  onChange,
  onSubmit,
  suggestions,
  isLoadingSuggestions = false,
  onSelectSuggestion,
  label = "Search products",
  hideLabel = false,
}: SearchBarProps) {
  const inputId = useId();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSubmit?.(value);
  }

  // Batch 3 — Stitch hero glass search pill (COMPONENT-SPECS §5): a rounded
  // white pill with a leading search glyph, a borderless field, an optional
  // Clear control and a primary Search button (submits the same form — Enter
  // still works). Suggestions sit in a card directly under the pill.
  return (
    <div>
      <form onSubmit={handleSubmit} role="search">
        <label
          htmlFor={inputId}
          className={hideLabel ? "sr-only" : "mb-2 block font-label text-label-caps uppercase text-on-surface"}
        >
          {label}
        </label>
        <div className="flex items-center gap-2 rounded-full border border-outline-variant/40 bg-surface-container-lowest p-1.5 pl-5 shadow-2xl">
          <Icon name="search" className="h-5 w-5 text-on-surface-variant" />
          <input
            id={inputId}
            type="search"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder="Search by product name"
            className="min-h-11 min-w-0 flex-1 rounded-control bg-transparent px-2 font-body text-body-md text-on-surface placeholder:text-on-surface-variant/70 focus:outline-none"
          />
          {value.length > 0 && (
            <button
              type="button"
              onClick={() => onChange("")}
              className="inline-flex min-h-11 items-center rounded-full px-3 font-label text-label-caps uppercase text-on-surface-variant transition-colors duration-200 hover:bg-surface-container hover:text-on-surface"
            >
              Clear
            </button>
          )}
          <button
            type="submit"
            className="inline-flex min-h-11 items-center gap-2 rounded-full bg-primary px-4 font-label text-label-caps uppercase text-on-primary transition-colors duration-200 hover:bg-primary-container tablet:px-6"
          >
            <Icon name="search" className="h-4 w-4" />
            <span className="sr-only tablet:not-sr-only">Search</span>
          </button>
        </div>
      </form>

      {isLoadingSuggestions && (
        <p
          role="status"
          aria-live="polite"
          className="mt-2 rounded-card bg-surface-container-lowest px-4 py-3 font-body text-sm text-on-surface-variant shadow-lg"
        >
          Loading suggestions…
        </p>
      )}

      {!isLoadingSuggestions && suggestions && suggestions.length === 0 && (
        <p className="mt-2 rounded-card bg-surface-container-lowest px-4 py-3 font-body text-sm text-on-surface-variant shadow-lg">
          No suggestions found.
        </p>
      )}

      {!isLoadingSuggestions && suggestions && suggestions.length > 0 && (
        <ul className="mt-2 rounded-card border border-outline-variant/30 bg-surface-container-lowest p-2 text-left shadow-xl">
          {suggestions.map((suggestion, index) => (
            <li key={index}>
              <button
                type="button"
                onClick={() => onSelectSuggestion?.(suggestion)}
                className="flex min-h-11 w-full items-center gap-3 rounded-control px-3 text-left font-body text-body-md text-on-surface transition-colors duration-200 hover:bg-surface-container-low"
              >
                <Icon name="search" className="h-4 w-4 text-on-surface-variant" />
                {suggestion.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
