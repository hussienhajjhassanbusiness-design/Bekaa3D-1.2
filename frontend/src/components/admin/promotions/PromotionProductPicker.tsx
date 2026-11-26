"use client";

import { useId, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { TextField } from "@/components/forms/TextField";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { useAdminProducts } from "@/lib/admin/products/useAdminProducts";
import { productsAdminApi, productsAdminKeys } from "@/lib/admin/products/productsAdminApi";
import { useDebouncedValue } from "@/lib/shared/useDebouncedValue";

export interface PromotionProductPickerProps {
  selectedIds: readonly string[];
  onChange: (ids: string[]) => void;
  error?: string;
  disabled?: boolean;
}

// The products of a `selected`-scope promotion. Searches the real admin
// product list (GET /api/v1/admin/products?q=), live products only; names of
// already-chosen products outside the current results are read by id. The
// backend re-checks every id on save (existing, not deleted).
export function PromotionProductPicker({ selectedIds, onChange, error, disabled }: PromotionProductPickerProps) {
  const groupId = useId();
  const errorId = useId();
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search.trim(), 300);
  const results = useAdminProducts({ q: q || undefined, limit: 20 });
  const shown = results.data?.items ?? [];
  const shownIds = new Set(shown.map((p) => p.id));
  const missing = selectedIds.filter((id) => !shownIds.has(id));
  const chosen = useQueries({
    queries: missing.map((id) => ({
      queryKey: productsAdminKeys.detail(id),
      queryFn: () => productsAdminApi.getProduct(id),
    })),
  });
  const names = new Map<string, string>(shown.map((p) => [p.id, p.name]));
  chosen.forEach((query, index) => {
    if (query.data) names.set(missing[index]!, query.data.name);
  });
  const selected = new Set(selectedIds);

  function toggle(id: string, checked: boolean) {
    onChange(checked ? [...selectedIds, id] : selectedIds.filter((value) => value !== id));
  }

  return (
    <div className="flex flex-col gap-4">
      <TextField
        label="Find products"
        type="search"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        disabled={disabled}
        leadingIcon="search"
      />
      <fieldset
        aria-describedby={error ? errorId : undefined}
        aria-labelledby={groupId}
        className="flex flex-col gap-2"
        disabled={disabled}
      >
        <legend id={groupId} className="mb-1 font-label text-label-sm uppercase text-on-surface">
          Products in this promotion ({selectedIds.length} chosen)
        </legend>
        {results.isLoading && <p className="text-body-md text-on-surface-variant">Loading products…</p>}
        {!results.isLoading && shown.length === 0 && (
          <p className="text-body-md text-on-surface-variant">No products match this search.</p>
        )}
        <ul className="max-h-72 divide-y divide-outline-variant/30 overflow-y-auto rounded-control border border-outline-variant/40">
          {shown.map((product) => (
            <li key={product.id}>
              <label className="flex min-h-11 cursor-pointer items-center gap-3 px-3 py-2 hover:bg-surface-container-low">
                <input
                  type="checkbox"
                  checked={selected.has(product.id)}
                  onChange={(event) => toggle(product.id, event.target.checked)}
                  className="h-5 w-5 shrink-0 rounded border-outline-variant text-primary focus-visible:ring-2 focus-visible:ring-primary"
                />
                <span className="min-w-0 flex-1 break-words text-body-md text-on-surface">{product.name}</span>
                <span className="shrink-0 font-label text-label-sm uppercase text-on-surface-variant">
                  {product.type === "stl" ? "STL" : "Physical"} ·{" "}
                  <PriceDisplay amountCents={product.price.amount_cents} currency={product.price.currency} />
                </span>
              </label>
            </li>
          ))}
        </ul>
        {missing.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {missing.map((id) => (
              <span
                key={id}
                className="inline-flex items-center gap-2 rounded-full bg-surface-container-high px-3 py-1 text-body-md text-on-surface"
              >
                {names.get(id) ?? "Chosen product"}
                <button
                  type="button"
                  onClick={() => toggle(id, false)}
                  className="font-semibold text-primary underline underline-offset-2"
                  aria-label={`Remove ${names.get(id) ?? "this product"}`}
                >
                  Remove
                </button>
              </span>
            ))}
          </div>
        )}
      </fieldset>
      {error && (
        <p id={errorId} role="alert" className="text-body-md text-error">
          {error}
        </p>
      )}
    </div>
  );
}
