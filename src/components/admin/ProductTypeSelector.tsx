"use client";

import { useId } from "react";

// Internal frontend UI literals — NOT a claim about the backend's actual
// discriminator field name or enum strings (both NEEDS BACKEND
// CONFIRMATION, FVS-011-IMPLEMENTATION-PLAN.md §1). A future API adapter
// maps these onto whatever the real contract defines.
export type ProductTypeOption = "physical" | "stl";

export interface ProductTypeSelectorProps {
  mode: "create" | "edit";
  value: ProductTypeOption;
  onChange: (next: ProductTypeOption) => void;
}

const OPTIONS: { value: ProductTypeOption; label: string }[] = [
  { value: "physical", label: "Physical" },
  { value: "stl", label: "STL (digital)" },
];

// #FVS011-PRODUCT-TYPE
//
// Product type is immutable after creation (vertical-slice-plan.md
// VS-011's own Logic line: "Immutable product type"). Edit mode disables
// both options AND explains why via aria-describedby on the radiogroup —
// never a bare grayed-out look with no accessible reason. One shared
// selector for both modes, not two components, since the only
// difference is "locked or not."
export function ProductTypeSelector({ mode, value, onChange }: ProductTypeSelectorProps) {
  const name = useId();
  const explanationId = useId();
  const isLocked = mode === "edit";

  return (
    <fieldset>
      <legend className="text-label font-semibold uppercase tracking-label text-text-primary">Product type</legend>
      <div role="radiogroup" aria-describedby={isLocked ? explanationId : undefined} className="mt-2 flex gap-4">
        {OPTIONS.map((option) => (
          <label key={option.value} className="flex items-center gap-2 text-body text-text-primary">
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              disabled={isLocked}
              onChange={() => onChange(option.value)}
            />
            {option.label}
          </label>
        ))}
      </div>
      {isLocked && (
        <p id={explanationId} className="mt-2 text-caption text-text-secondary">
          Product type can&apos;t be changed after creation.
        </p>
      )}
    </fieldset>
  );
}
