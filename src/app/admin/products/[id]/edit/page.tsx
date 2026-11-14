"use client";

import { AdminBackLink } from "@/components/admin/adminUi";
import { useState } from "react";
import { useParams } from "next/navigation";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Alert } from "@/components/feedback/Alert";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { ProductForm } from "@/components/admin/ProductForm";
import { ImageGallery } from "@/components/admin/ImageGallery";
import { FileUploader, type UploadDriver } from "@/components/forms/FileUploader";
import type { UploadValidationConfig } from "@/components/forms/uploadTypes";
import { useAdminProduct } from "@/lib/admin/products/useAdminProduct";
import { useAdminProductUpdate } from "@/lib/admin/products/useAdminProductMutations";
import { useProductFormReferenceData } from "@/lib/admin/products/useProductFormReferenceData";
import {
  useProductImageUpload,
  useProductImageAltTextUpdate,
  useProductImageSetCover,
  useProductImageReorder,
  useProductImageDelete,
} from "@/lib/admin/products/useProductImageMutations";
import {
  toFormValues,
  toUpdateBody,
  toGalleryImages,
  isPhysicalRequiredFieldsComplete,
  isValidSlugFormat,
  describeProductError,
  type ProductFieldErrors,
} from "@/lib/admin/products/productAdminAdapter";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import type { ProductFormValues } from "@/lib/admin/products/productAdminTypes";

const LOAD_ERROR_MESSAGE = "Couldn't load this product. Please try again.";

const PRODUCT_IMAGE_UPLOAD_CONFIG: UploadValidationConfig = {
  allowedMimeTypes: ["image/jpeg", "image/png", "image/webp"],
  maxBytes: 10 * 1024 * 1024,
  maxFiles: 20,
};

function isNotFound(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "kind" in error &&
    (error as { kind: unknown }).kind === "http" &&
    (error as { status?: unknown }).status === 404
  );
}

export default function AdminProductEditPage() {
  const params = useParams<{ id: string }>();
  const productId = params.id;

  const { data: product, isLoading, isError, error, refetch } = useAdminProduct(productId);
  const updateMutation = useAdminProductUpdate(productId);
  const referenceData = useProductFormReferenceData();
  const uploadMutation = useProductImageUpload(productId);
  const altTextMutation = useProductImageAltTextUpdate(productId);
  const setCoverMutation = useProductImageSetCover(productId);
  const reorderMutation = useProductImageReorder(productId);
  const deleteMutation = useProductImageDelete(productId);

  // Initializes the form exactly once per product id, using React's own
  // "adjust state while rendering" pattern (never an effect — a
  // background refetch, e.g. an image mutation's own invalidation, must
  // not clobber in-progress edits, and react-hooks/set-state-in-effect
  // forbids a plain setState-in-effect for this anyway). A version
  // conflict resets this explicitly from handleSubmit's catch branch
  // instead, by storing the same product id with freshly-fetched values
  // — a deliberate, user-visible reset, not a background sync.
  const [formState, setFormState] = useState<{ productId: string; values: ProductFormValues } | null>(null);
  if (product && formState?.productId !== product.id) {
    setFormState({ productId: product.id, values: toFormValues(product) });
  }
  const form = formState && product && formState.productId === product.id ? formState.values : null;
  function setForm(next: ProductFormValues) {
    if (product) {
      setFormState({ productId: product.id, values: next });
    }
  }

  const [fieldErrors, setFieldErrors] = useState<ProductFieldErrors | undefined>(undefined);
  const [bannerMessage, setBannerMessage] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (isError) {
    return isNotFound(error) ? <NotFoundContent /> : <Alert variant="error" message={LOAD_ERROR_MESSAGE} />;
  }

  if (!product || !form) {
    return <NotFoundContent />;
  }

  async function handleSubmit() {
    setBannerMessage(null);
    const errors: ProductFieldErrors = {};
    if (!form!.name) errors.name = "Name is required.";
    if (!form!.slug || !isValidSlugFormat(form!.slug)) {
      errors.slug = "Enter a slug using lowercase letters, digits, and single hyphens.";
    }
    if (!form!.categoryId) errors.categoryId = "Select a category.";
    if (form!.priceCents === null) errors.priceCents = "Enter a price.";
    if (!isPhysicalRequiredFieldsComplete(form!)) {
      errors.productionLeadTimeDays = errors.productionLeadTimeDays ?? "Required for a physical product.";
    }
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }
    setFieldErrors(undefined);

    try {
      await updateMutation.mutateAsync(toUpdateBody(form!, product!.version));
    } catch (error) {
      const result = describeProductError(error);
      if (result.isVersionConflict) {
        const fresh = await refetch();
        if (fresh.data) {
          setForm(toFormValues(fresh.data));
        }
        setBannerMessage(result.bannerMessage ?? null);
      } else if (result.fieldErrors) {
        setFieldErrors(result.fieldErrors);
      } else {
        setBannerMessage(result.bannerMessage ?? null);
      }
    }
  }

  const uploadDriver: UploadDriver = async (file) => {
    try {
      await uploadMutation.mutateAsync({ file });
      return { ok: true };
    } catch (error) {
      return { ok: false, reason: describeAdminError(error) };
    }
  };

  async function handleUpdateAltText(imageId: string, nextAltText: string) {
    setImageError(null);
    try {
      await altTextMutation.mutateAsync({ imageId, altText: nextAltText === "" ? null : nextAltText });
    } catch (error) {
      setImageError(describeAdminError(error));
    }
  }

  async function handleSetCover(imageId: string) {
    setImageError(null);
    try {
      await setCoverMutation.mutateAsync(imageId);
    } catch (error) {
      setImageError(describeAdminError(error));
    }
  }

  async function handleReorder(nextIds: string[]) {
    setImageError(null);
    try {
      await reorderMutation.mutateAsync(nextIds);
    } catch (error) {
      setImageError(describeAdminError(error));
    }
  }

  // Returns whether the delete succeeded so the gallery closes its
  // confirmation dialog only on success (Phase 5A final defect).
  async function handleDeleteImage(imageId: string): Promise<boolean> {
    setImageError(null);
    try {
      await deleteMutation.mutateAsync(imageId);
      return true;
    } catch (error) {
      setImageError(describeAdminError(error));
      return false;
    }
  }

  return (
    <>
      <div>
        <AdminBackLink href={`/admin/products/${product.id}`}>Back to product</AdminBackLink>
      </div>
      <h1 className="mt-2 break-words font-headline text-headline-lg text-on-surface">Edit {product.name}</h1>
      {bannerMessage && (
        <div className="mt-4">
          <Alert variant="error" message={bannerMessage} />
        </div>
      )}

      {/* D5 split: form (7) | images (5) from 1280; stacked below. */}
      <div className="mt-6 grid max-w-content gap-gutter xl:grid-cols-12 xl:items-start">
        <div className="min-w-0 xl:col-span-7">
          <ProductForm
            mode="edit"
            value={form}
            onChange={setForm}
            categories={referenceData.categories}
            materials={referenceData.materials}
            colours={referenceData.colours}
            fieldErrors={fieldErrors}
            isSubmitting={updateMutation.isPending}
            submitLabel="Save changes"
            onSubmit={() => void handleSubmit()}
          />
        </div>

        <section
          aria-labelledby="product-images-heading"
          className="min-w-0 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm tablet:p-6 xl:col-span-5"
        >
          <h2 id="product-images-heading" className="font-headline text-headline-md text-on-surface">
            Images
          </h2>
          {imageError && (
            <div className="mt-4">
              <Alert variant="error" message={imageError} />
            </div>
          )}
          <div className="mt-4">
            <FileUploader label="Add images" config={PRODUCT_IMAGE_UPLOAD_CONFIG} driver={uploadDriver} multiple />
          </div>
          <div className="mt-4">
            <ImageGallery
              images={toGalleryImages(product.images, product.name)}
              onReorder={(nextIds) => void handleReorder(nextIds)}
              onSetCover={(imageId) => void handleSetCover(imageId)}
              onDelete={handleDeleteImage}
              onUpdateAltText={(imageId, nextAltText) => void handleUpdateAltText(imageId, nextAltText)}
              isDeleting={deleteMutation.isPending}
              isUpdatingAltText={altTextMutation.isPending}
            />
          </div>
        </section>
      </div>
    </>
  );
}
