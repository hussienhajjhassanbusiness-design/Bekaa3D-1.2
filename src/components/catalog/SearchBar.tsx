"use client";

import { useId, type FormEvent } from "react";
import { Button } from "@/components/forms/Button";

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
}: SearchBarProps) {
  const inputId = useId();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSubmit?.(value);
  }

  return (
    <div>
      <form onSubmit={handleSubmit} role="search">
        <label htmlFor={inputId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
          {label}
        </label>
        <div className="mt-1 flex items-center gap-2">
          <input
            id={inputId}
            type="search"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            className="w-full rounded-sm border border-border-default px-3 py-2 text-body text-text-primary"
          />
          {value.length > 0 && (
            <Button type="button" onClick={() => onChange("")}>
              Clear
            </Button>
          )}
        </div>
      </form>

      {isLoadingSuggestions && (
        <p role="status" aria-live="polite" className="mt-2 text-caption text-text-secondary">
          Loading suggestions…
        </p>
      )}

      {!isLoadingSuggestions && suggestions && suggestions.length === 0 && (
        <p className="mt-2 text-caption text-text-secondary">No suggestions found.</p>
      )}

      {!isLoadingSuggestions && suggestions && suggestions.length > 0 && (
        <ul className="mt-2">
          {suggestions.map((suggestion, index) => (
            <li key={index}>
              <button
                type="button"
                onClick={() => onSelectSuggestion?.(suggestion)}
                className="w-full text-left text-body text-text-primary"
              >
                {suggestion.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
