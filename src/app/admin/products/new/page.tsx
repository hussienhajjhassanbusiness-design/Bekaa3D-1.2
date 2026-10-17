"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Alert } from "@/components/feedback/Alert";
import { ProductForm } from "@/components/admin/ProductForm";
import { useAdminProductCreate } from "@/lib/admin/products/useAdminProductMutations";
import { useProductFormReferenceData } from "@/lib/admin/products/useProductFormReferenceData";
import {
  isPhysicalRequiredFieldsComplete,
  isValidSlugFormat,
  toCreateBody,
  describeProductError,
  type ProductFieldErrors,
} from "@/lib/admin/products/productAdminAdapter";
import { EMPTY_PRODUCT_FORM_VALUES } from "@/lib/admin/products/productAdminTypes";

export default function AdminNewProductPage() {
  const router = useRouter();
  const createMutation = useAdminProductCreate();
  const referenceData = useProductFormReferenceData();
  const [form, setForm] = useState(EMPTY_PRODUCT_FORM_VALUES);
  const [fieldErrors, setFieldErrors] = useState<ProductFieldErrors | undefined>(undefined);
  const [bannerMessage, setBannerMessage] = useState<string | null>(null);

  async function handleSubmit() {
    setBannerMessage(null);
    const errors: ProductFieldErrors = {};
    if (!form.name) errors.name = "Name is required.";
    if (!form.slug || !isValidSlugFormat(form.slug)) {
      errors.slug = "Enter a slug using lowercase letters, digits, and single hyphens.";
    }
    if (!form.categoryId) errors.categoryId = "Select a category.";
    if (form.priceCents === null) errors.priceCents = "Enter a price.";
    if (!isPhysicalRequiredFieldsComplete(form)) {
      errors.productionLeadTimeDays = errors.productionLeadTimeDays ?? "Required for a physical product.";
    }
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }
    setFieldErrors(undefined);

    try {
      const created = await createMutation.mutateAsync(toCreateBody(form));
      router.push(`/admin/products/${created.id}/edit`);
    } catch (error) {
      const result = describeProductError(error);
      if (result.fieldErrors) {
        setFieldErrors(result.fieldErrors);
      } else {
        setBannerMessage(result.bannerMessage ?? null);
      }
    }
  }

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">New product</h1>
      {bannerMessage && <Alert variant="error" message={bannerMessage} />}
      <div className="mt-4 max-w-2xl">
        <ProductForm
          mode="create"
          value={form}
          onChange={setForm}
          categories={referenceData.categories}
          materials={referenceData.materials}
          colours={referenceData.colours}
          fieldErrors={fieldErrors}
          isSubmitting={createMutation.isPending}
          submitLabel="Create product"
          onSubmit={() => void handleSubmit()}
        />
      </div>
    </>
  );
}
