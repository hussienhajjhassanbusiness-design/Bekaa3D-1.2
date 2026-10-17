"use client";

import type { FormEvent } from "react";
import { TextField } from "@/components/forms/TextField";
import { SelectField } from "@/components/forms/SelectField";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { Button } from "@/components/forms/Button";
import { ProductTypeSelector, type ProductTypeOption } from "@/components/admin/ProductTypeSelector";
import type { ProductFormValues, PurchaseMode } from "@/lib/admin/products/productAdminTypes";
import type { ProductFieldErrors } from "@/lib/admin/products/productAdminAdapter";

export interface ProductFormOption {
  id: string;
  name: string;
}

export interface ProductFormProps {
  mode: "create" | "edit";
  value: ProductFormValues;
  onChange: (next: ProductFormValues) => void;
  categories: readonly ProductFormOption[];
  materials: readonly ProductFormOption[];
  colours: readonly ProductFormOption[];
  fieldErrors?: ProductFieldErrors;
  isSubmitting?: boolean;
  submitLabel?: string;
  onSubmit: () => void;
}

const PURCHASE_MODE_OPTIONS: { value: PurchaseMode; label: string }[] = [
  { value: "online_only", label: "Online only" },
  { value: "whatsapp_only", label: "WhatsApp only" },
  { value: "both", label: "Online and WhatsApp" },
];

function numberOrNull(raw: string): number | null {
  if (raw === "") return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

// #FVS011-PRODUCT-FORM
//
// A plain controlled component (not the generic RHF `Form`) — the
// required-field set genuinely depends on `value.type`, which a single
// static Zod schema can't express without a discriminated union that
// would add more complexity than it removes here. Client-side checks
// (slug format, physical-required completeness) are UX only — the
// server's 422/409 responses remain the real authority
// (bekaa3d-api-contract).
export function ProductForm({
  mode,
  value,
  onChange,
  categories,
  materials,
  colours,
  fieldErrors,
  isSubmitting = false,
  submitLabel = "Save",
  onSubmit,
}: ProductFormProps) {
  function patch(partial: Partial<ProductFormValues>) {
    onChange({ ...value, ...partial });
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <fieldset disabled={isSubmitting} className="contents">
        <section className="flex flex-col gap-4">
          <h2 className="text-h3 font-bold text-text-primary">Product type</h2>
          <ProductTypeSelector
            mode={mode}
            value={value.type as ProductTypeOption}
            onChange={(next) => patch({ type: next })}
          />
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-h3 font-bold text-text-primary">Basic information</h2>
          <TextField label="Name" value={value.name} onChange={(e) => patch({ name: e.target.value })} error={fieldErrors?.name} />
          <TextField
            label="Slug"
            hint="Lowercase letters, digits, and single hyphens only — not auto-generated from the name."
            value={value.slug}
            onChange={(e) => patch({ slug: e.target.value })}
            error={fieldErrors?.slug}
          />
          <SelectField
            label="Category"
            value={value.categoryId}
            onChange={(e) => patch({ categoryId: e.target.value })}
            error={fieldErrors?.categoryId}
          >
            <option value="">Select a category</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </SelectField>
          <MoneyInput
            label="Price"
            currencyLabel="USD"
            valueCents={value.priceCents}
            onChangeCents={(cents) => patch({ priceCents: cents })}
            error={fieldErrors?.priceCents}
          />
          <label className="block">
            <span className="text-label font-semibold uppercase tracking-label text-text-primary">Description</span>
            <textarea
              value={value.description}
              onChange={(e) => patch({ description: e.target.value })}
              rows={4}
              className="mt-1 w-full rounded-sm border border-border-default px-3 py-2 text-body text-text-primary"
            />
          </label>
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="text-h3 font-bold text-text-primary">Visibility and availability</h2>
          <label className="flex items-center gap-2 text-body text-text-primary">
            <input type="checkbox" checked={value.isVisible} onChange={(e) => patch({ isVisible: e.target.checked })} />
            Visible on the storefront
          </label>
          <label className="flex items-center gap-2 text-body text-text-primary">
            <input type="checkbox" checked={value.isFeatured} onChange={(e) => patch({ isFeatured: e.target.checked })} />
            Featured
          </label>
          <label className="flex items-center gap-2 text-body text-text-primary">
            <input type="checkbox" checked={value.isAvailable} onChange={(e) => patch({ isAvailable: e.target.checked })} />
            Available for purchase
          </label>
        </section>

        {value.type === "physical" && (
          <section className="flex flex-col gap-4">
            <h2 className="text-h3 font-bold text-text-primary">Physical product details</h2>
            <SelectField label="Material" value={value.materialId} onChange={(e) => patch({ materialId: e.target.value })}>
              <option value="">None</option>
              {materials.map((material) => (
                <option key={material.id} value={material.id}>
                  {material.name}
                </option>
              ))}
            </SelectField>
            <SelectField label="Colour" value={value.colourId} onChange={(e) => patch({ colourId: e.target.value })}>
              <option value="">None</option>
              {colours.map((colour) => (
                <option key={colour.id} value={colour.id}>
                  {colour.name}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Purchase mode"
              value={value.purchaseMode}
              onChange={(e) => patch({ purchaseMode: e.target.value as PurchaseMode })}
            >
              {PURCHASE_MODE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </SelectField>
            <TextField
              label="Production lead time (days)"
              type="number"
              min={0}
              value={value.productionLeadTimeDays ?? ""}
              onChange={(e) => patch({ productionLeadTimeDays: numberOrNull(e.target.value) })}
              error={fieldErrors?.productionLeadTimeDays}
            />
            <TextField
              label="Batch size"
              type="number"
              min={1}
              value={value.batchSize ?? ""}
              onChange={(e) => patch({ batchSize: numberOrNull(e.target.value) })}
              error={fieldErrors?.batchSize}
            />
            <TextField
              label="Max quantity per order line"
              type="number"
              min={1}
              value={value.maxQuantityPerLine ?? ""}
              onChange={(e) => patch({ maxQuantityPerLine: numberOrNull(e.target.value) })}
              error={fieldErrors?.maxQuantityPerLine}
            />
            <TextField
              label="Weight (grams)"
              type="number"
              min={1}
              value={value.weightGrams ?? ""}
              onChange={(e) => patch({ weightGrams: numberOrNull(e.target.value) })}
              error={fieldErrors?.weightGrams}
            />
            <div className="grid grid-cols-3 gap-3">
              <TextField
                label="Length (mm)"
                type="number"
                min={1}
                value={value.lengthMm ?? ""}
                onChange={(e) => patch({ lengthMm: numberOrNull(e.target.value) })}
              />
              <TextField
                label="Width (mm)"
                type="number"
                min={1}
                value={value.widthMm ?? ""}
                onChange={(e) => patch({ widthMm: numberOrNull(e.target.value) })}
              />
              <TextField
                label="Height (mm)"
                type="number"
                min={1}
                value={value.heightMm ?? ""}
                onChange={(e) => patch({ heightMm: numberOrNull(e.target.value) })}
              />
            </div>
          </section>
        )}

        <section className="flex flex-col gap-4">
          <h2 className="text-h3 font-bold text-text-primary">SEO</h2>
          <TextField label="SEO title" value={value.seoTitle} onChange={(e) => patch({ seoTitle: e.target.value })} />
          <label className="block">
            <span className="text-label font-semibold uppercase tracking-label text-text-primary">SEO description</span>
            <textarea
              value={value.seoDescription}
              onChange={(e) => patch({ seoDescription: e.target.value })}
              rows={2}
              className="mt-1 w-full rounded-sm border border-border-default px-3 py-2 text-body text-text-primary"
            />
          </label>
          <TextField
            label="Social share image URL"
            value={value.ogImageUrl}
            onChange={(e) => patch({ ogImageUrl: e.target.value })}
            error={fieldErrors?.ogImageUrl}
          />
        </section>

        <Button type="submit" isLoading={isSubmitting}>
          {submitLabel}
        </Button>
      </fieldset>
    </form>
  );
}
