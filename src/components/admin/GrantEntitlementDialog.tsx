"use client";

import { useId, useState } from "react";
import { Button } from "@/components/forms/Button";
import { DialogShell } from "@/components/feedback/DialogShell";
import { SearchableCombobox } from "./SearchableCombobox";
import { selectableStlProducts, type CustomerOption, type ProductOption } from "@/lib/admin/entitlementGrantModels";

export interface GrantEntitlementDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (customerId: string, productId: string) => void;
  isSubmitting?: boolean;
  errorMessage?: string | null;
  customerOptions?: readonly CustomerOption[];
  productOptions?: readonly ProductOption[];
  fixedCustomer?: CustomerOption;
  fixedProduct?: ProductOption;
}

// #FVS019-GRANT-ENTITLEMENT-DIALOG
//
// Presentational only — no network, no query, no backend request DTO.
// Reuses the shared `DialogShell` (no second focus-trap implementation)
// and `SearchableCombobox`. Supports a preselected customer/product
// fixed by the surrounding route context (customer-detail vs
// product-detail entry point) without forcing the caller to re-select
// something already known. The product picker is filtered to STL
// products client-side ONLY for UX — #SECURITY-ENTITLEMENT-GRANT: the
// server remains the sole authority and MUST independently reject a
// non-STL grant. `errorMessage` is an already-safe string from a future
// adapter — this component never parses a raw backend error, and never
// invents an "already entitled" conflict code itself.
export function GrantEntitlementDialog({
  open,
  onClose,
  onConfirm,
  isSubmitting = false,
  errorMessage = null,
  customerOptions = [],
  productOptions = [],
  fixedCustomer,
  fixedProduct,
}: GrantEntitlementDialogProps) {
  const titleId = useId();

  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(fixedCustomer?.id ?? null);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(fixedProduct?.id ?? null);

  const customerId = fixedCustomer?.id ?? selectedCustomerId;
  const productId = fixedProduct?.id ?? selectedProductId;
  const canConfirm = Boolean(customerId) && Boolean(productId);

  return (
    <DialogShell open={open} onClose={onClose} isBusy={isSubmitting} labelledBy={titleId}>
      <h2 id={titleId} className="text-h3 font-bold text-text-primary">
        Grant STL entitlement
      </h2>

      <div className="mt-4">
        {fixedCustomer ? (
          <p className="text-body text-text-primary">{fixedCustomer.displayLabel}</p>
        ) : (
          <SearchableCombobox
            label="Customer"
            options={customerOptions.map((customer) => ({ id: customer.id, label: customer.displayLabel }))}
            value={selectedCustomerId}
            onChange={setSelectedCustomerId}
          />
        )}
      </div>

      <div className="mt-4">
        {fixedProduct ? (
          <p className="text-body text-text-primary">{fixedProduct.displayLabel}</p>
        ) : (
          <SearchableCombobox
            label="STL product"
            options={selectableStlProducts(productOptions).map((product) => ({ id: product.id, label: product.displayLabel }))}
            value={selectedProductId}
            onChange={setSelectedProductId}
          />
        )}
      </div>

      {errorMessage && (
        <p role="alert" className="mt-4 text-caption text-danger">
          {errorMessage}
        </p>
      )}

      <div className="mt-4 flex justify-end gap-2">
        <Button type="button" onClick={onClose} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button
          type="button"
          onClick={() => customerId && productId && onConfirm(customerId, productId)}
          disabled={!canConfirm || isSubmitting}
          isLoading={isSubmitting}
        >
          Grant
        </Button>
      </div>
    </DialogShell>
  );
}
