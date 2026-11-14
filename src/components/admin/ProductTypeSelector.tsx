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
      <legend className="font-label text-label-sm uppercase text-on-surface-variant">Product type</legend>
      <div
        role="radiogroup"
        aria-describedby={isLocked ? explanationId : undefined}
        className="mt-2 grid gap-3 tablet:grid-cols-2"
      >
        {OPTIONS.map((option) => (
          <label
            key={option.value}
            className={`flex min-h-12 items-center gap-3 rounded-control border p-3 font-body text-body-md text-on-surface ${
              value === option.value ? "border-primary bg-primary/5 font-semibold" : "border-outline-variant"
            } ${isLocked ? "cursor-not-allowed opacity-70" : "cursor-pointer hover:bg-surface-container-low"}`}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              disabled={isLocked}
              onChange={() => onChange(option.value)}
              className="h-5 w-5 accent-primary"
            />
            {option.label}
          </label>
        ))}
      </div>
      {isLocked && (
        <p id={explanationId} className="mt-2 text-caption text-on-surface-variant">
          Product type can&apos;t be changed after creation.
        </p>
      )}
    </fieldset>
  );
}
