import type { ApiError } from "@/lib/api/ApiError";
import type { ReferenceDataDraft, ReferenceDataEntry, ReferenceDataFieldErrors } from "@/components/admin/referenceDataTypes";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import type { ReferenceDataCreateInput, ReferenceDataResource, RawReferenceDetail } from "./referenceDataAdminTypes";

export function toReferenceDataEntry(raw: RawReferenceDetail): ReferenceDataEntry {
  return {
    id: raw.id,
    name: raw.name,
    isArchived: raw.deleted_at !== null,
    isActive: raw.is_active,
    // Categories only — the generic "swatchValue" slot (historically
    // sized for a colour swatch) doubles as the slug display/edit field
    // here; materials/colours have no second field at all and leave
    // this undefined.
    swatchValue: raw.slug,
  };
}

export function toCreateInput(resource: ReferenceDataResource, draft: ReferenceDataDraft): ReferenceDataCreateInput {
  return { name: draft.name, slug: resource === "categories" ? draft.swatchValue : undefined };
}

// The slug-holds-swatchValue field maps back to the one field name a
// SLUG_CONFLICT/VALIDATION_ERROR about it can land on — "name" for
// materials/colours (which only have a name), "swatchValue" (the slug
// slot) for categories.
function conflictFieldFor(resource: ReferenceDataResource): "name" | "swatchValue" {
  return resource === "categories" ? "swatchValue" : "name";
}

export interface ReferenceDataErrorResult {
  fieldErrors?: ReferenceDataFieldErrors;
  bannerMessage?: string;
}

function isApiError(error: unknown): error is ApiError {
  return typeof error === "object" && error !== null && "kind" in error;
}

// SLUG_CONFLICT (and a VALIDATION_ERROR naming the same field) render
// inline, next to the field the admin is actually editing; every other
// error (CATEGORY_IN_USE, INVALID_STATE_TRANSITION, NOT_FOUND, generic)
// is a page-level banner — there's no specific field to blame.
export function describeReferenceDataError(resource: ReferenceDataResource, error: unknown): ReferenceDataErrorResult {
  if (isApiError(error) && error.kind === "http") {
    if (error.code === "SLUG_CONFLICT") {
      const field = conflictFieldFor(resource);
      const message = resource === "categories" ? "That slug is already in use." : "That name is already in use.";
      return { fieldErrors: { [field]: message } };
    }

    if (error.code === "VALIDATION_ERROR" && error.errors && error.errors.length > 0) {
      const target = error.errors.find((item) => {
        const fieldName = item.loc.at(-1);
        return fieldName === "name" || fieldName === "slug";
      });
      if (target) {
        const fieldName = target.loc.at(-1);
        const field = fieldName === "slug" ? conflictFieldFor(resource) : "name";
        return { fieldErrors: { [field]: "Enter a valid value." } };
      }
    }
  }

  return { bannerMessage: describeAdminError(error) };
}
