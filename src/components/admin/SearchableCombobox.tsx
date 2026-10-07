"use client";

import { useId, useState, type ChangeEvent, type KeyboardEvent } from "react";

export interface ComboboxOption {
  id: string;
  label: string;
}

export interface SearchableComboboxProps {
  label: string;
  options: readonly ComboboxOption[];
  value: string | null;
  onChange: (id: string) => void;
  placeholder?: string;
}

// #FVS019-SEARCHABLE-COMBOBOX
//
// A small, fully keyboard-accessible single-select combobox — built
// because no existing accessible combobox was found anywhere in the
// repository (audited first, FVS-019-IMPLEMENTATION-PLAN.md §0), and a
// large UI package was not installed solely for this. Filtering is
// purely local (substring match over the already-supplied `options`
// prop); a real, debounced server-search integration stays contract-
// gated, same precedent as FVS-013's SearchBar — this component itself
// never calls the network.
export function SearchableCombobox({ label, options, onChange, placeholder }: SearchableComboboxProps) {
  const inputId = useId();
  const listboxId = useId();

  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  // -1 means "no option highlighted yet" — the first ArrowDown moves to
  // index 0 rather than skipping it.
  const [activeIndex, setActiveIndex] = useState(-1);

  const filteredOptions = options.filter((option) => option.label.toLowerCase().includes(query.toLowerCase()));

  function openWithQuery(nextQuery: string) {
    setQuery(nextQuery);
    setIsOpen(true);
    setActiveIndex(-1);
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    openWithQuery(event.target.value);
  }

  function selectOption(option: ComboboxOption) {
    onChange(option.id);
    setQuery(option.label);
    setIsOpen(false);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setIsOpen(true);
      setActiveIndex((index) => Math.min(index + 1, filteredOptions.length - 1));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const active = filteredOptions[activeIndex];
      if (isOpen && active) {
        selectOption(active);
      }
      return;
    }
    if (event.key === "Escape") {
      setIsOpen(false);
    }
  }

  const activeOptionId =
    isOpen && activeIndex >= 0 && filteredOptions[activeIndex] ? `${listboxId}-option-${activeIndex}` : undefined;

  return (
    <div>
      <label htmlFor={inputId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
        {label}
      </label>
      <input
        id={inputId}
        type="text"
        role="combobox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        aria-activedescendant={activeOptionId}
        autoComplete="off"
        value={query}
        placeholder={placeholder}
        onChange={handleInputChange}
        onFocus={() => {
          setIsOpen(true);
          setActiveIndex(-1);
        }}
        onKeyDown={handleKeyDown}
        className="mt-1 w-full rounded-sm border border-border-default px-3 py-2 text-body text-text-primary"
      />

      {isOpen && (
        <ul id={listboxId} role="listbox" className="mt-1 rounded-sm border border-border-default bg-white">
          {filteredOptions.length === 0 ? (
            <li className="px-3 py-2 text-caption text-text-secondary">No results found.</li>
          ) : (
            filteredOptions.map((option, index) => (
              <li
                key={option.id}
                id={`${listboxId}-option-${index}`}
                role="option"
                aria-selected={index === activeIndex}
                onMouseDown={(event) => {
                  event.preventDefault();
                  selectOption(option);
                }}
                className={`cursor-pointer px-3 py-2 text-body text-text-primary ${
                  index === activeIndex ? "bg-neutral-100" : ""
                }`}
              >
                {option.label}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
