import type { ApiError } from "@/lib/api/ApiError";
import type { GalleryImageModel } from "@/components/admin/ImageGallery";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import type { ProductFormValues, RawAdminProductDetail, RawProductImage } from "./productAdminTypes";

// `url` is opaque and ready-to-use (B4/P1-7) — never parsed or rebuilt,
// just passed straight through as `src`. Images come back pre-sorted
// by `sort_order` from the backend; defensively re-sort anyway since
// nothing in the contract guarantees list order survives every response
// path.
export function toGalleryImages(images: readonly RawProductImage[], fallbackLabel: string): GalleryImageModel[] {
  return [...images]
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((image) => ({
      id: image.id,
      src: image.url,
      accessibleLabel: image.alt_text ?? fallbackLabel,
      altText: image.alt_text ?? "",
      isCover: image.is_cover,
    }));
}

export function toFormValues(raw: RawAdminProductDetail): ProductFormValues {
  return {
    type: raw.type,
    categoryId: raw.category_id,
    name: raw.name,
    slug: raw.slug,
    priceCents: raw.price.amount_cents,
    description: raw.description ?? "",
    seoTitle: raw.seo_title ?? "",
    seoDescription: raw.seo_description ?? "",
    ogImageUrl: raw.og_image_url ?? "",
    isVisible: raw.is_visible,
    isFeatured: raw.is_featured,
    isAvailable: raw.is_available,
    materialId: raw.material_id ?? "",
    colourId: raw.colour_id ?? "",
    purchaseMode: raw.purchase_mode ?? "online_only",
    productionLeadTimeDays: raw.production_lead_time_days,
    batchSize: raw.batch_size,
    maxQuantityPerLine: raw.max_quantity_per_line,
    weightGrams: raw.weight_grams,
    lengthMm: raw.dimensions?.length_mm ?? null,
    widthMm: raw.dimensions?.width_mm ?? null,
    heightMm: raw.dimensions?.height_mm ?? null,
  };
}

// Fields common to both product types, sent verbatim every write (PATCH
// semantics: a field present here always means "set to this" — the form
// is always pre-filled from the authoritative read, so this is never a
// partial/diffed body, just never includes a physical-only field for an
// STL product, per AGENTS.md: "physical-only fields must not be sent
// for STL").
function buildCommonBody(form: ProductFormValues): Record<string, unknown> {
  const body: Record<string, unknown> = {
    category_id: form.categoryId,
    name: form.name,
    slug: form.slug,
    price: { amount_cents: form.priceCents, currency: "USD" },
    description: form.description === "" ? null : form.description,
    seo_title: form.seoTitle === "" ? null : form.seoTitle,
    seo_description: form.seoDescription === "" ? null : form.seoDescription,
    og_image_url: form.ogImageUrl === "" ? null : form.ogImageUrl,
    is_visible: form.isVisible,
    is_featured: form.isFeatured,
    is_available: form.isAvailable,
  };

  if (form.type === "physical") {
    body.purchase_mode = form.purchaseMode;
    body.production_lead_time_days = form.productionLeadTimeDays;
    body.batch_size = form.batchSize;
    body.max_quantity_per_line = form.maxQuantityPerLine;
    body.material_id = form.materialId === "" ? null : form.materialId;
    body.colour_id = form.colourId === "" ? null : form.colourId;
    body.weight_grams = form.weightGrams;
    body.dimensions =
      form.lengthMm !== null && form.widthMm !== null && form.heightMm !== null
        ? { length_mm: form.lengthMm, width_mm: form.widthMm, height_mm: form.heightMm }
        : null;
  }

  return body;
}

export function toCreateBody(form: ProductFormValues): Record<string, unknown> {
  return { type: form.type, ...buildCommonBody(form) };
}

// `type` is immutable and never sent on PATCH (extra_forbidden 422) —
// version always travels in the body here (DELETE is the query-string
// exception, handled in productsAdminApi.ts directly).
export function toUpdateBody(form: ProductFormValues, version: number): Record<string, unknown> {
  return { ...buildCommonBody(form), version };
}

const SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;

export function isValidSlugFormat(slug: string): boolean {
  return SLUG_PATTERN.test(slug);
}

// Client-side-only completeness check for the fields the backend's own
// prose contract calls "physical only, required" — a courtesy for fast
// feedback, never authoritative (bekaa3d-api-contract): the server's own
// 422 is still the final word if this ever disagrees with it.
export function isPhysicalRequiredFieldsComplete(form: ProductFormValues): boolean {
  if (form.type !== "physical") {
    return true;
  }
  return form.productionLeadTimeDays !== null && form.batchSize !== null && form.maxQuantityPerLine !== null;
}

function isApiError(error: unknown): error is ApiError {
  return typeof error === "object" && error !== null && "kind" in error;
}

export type ProductFieldErrors = Partial<Record<string, string>>;

export interface ProductErrorResult {
  fieldErrors?: ProductFieldErrors;
  bannerMessage?: string;
  isVersionConflict?: boolean;
}

const LOC_TO_FORM_FIELD: Record<string, string> = {
  category_id: "categoryId",
  name: "name",
  slug: "slug",
  price: "priceCents",
  purchase_mode: "purchaseMode",
  production_lead_time_days: "productionLeadTimeDays",
  batch_size: "batchSize",
  max_quantity_per_line: "maxQuantityPerLine",
  material_id: "materialId",
  colour_id: "colourId",
  weight_grams: "weightGrams",
  dimensions: "lengthMm",
  og_image_url: "ogImageUrl",
};

export function describeProductError(error: unknown): ProductErrorResult {
  if (isApiError(error) && error.kind === "http") {
    if (error.code === "VERSION_CONFLICT") {
      return {
        isVersionConflict: true,
        bannerMessage: "This product was changed by someone else. Review the latest version below and try again.",
      };
    }
    if (error.code === "SLUG_CONFLICT") {
      return { fieldErrors: { slug: "That slug is already in use by another live product." } };
    }
    if (error.code === "VALIDATION_ERROR" && error.errors && error.errors.length > 0) {
      const fieldErrors: ProductFieldErrors = {};
      for (const item of error.errors) {
        const backendField = item.loc.at(-1);
        const formField = typeof backendField === "string" ? LOC_TO_FORM_FIELD[backendField] : undefined;
        if (formField) {
          fieldErrors[formField] = "Enter a valid value for this field.";
        }
      }
      if (Object.keys(fieldErrors).length > 0) {
        return { fieldErrors };
      }
    }
  }

  return { bannerMessage: describeAdminError(error) };
}
