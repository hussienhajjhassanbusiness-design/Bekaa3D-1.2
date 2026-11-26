import type { ApiError } from "@/lib/api/ApiError";
import { mapValidationErrorsToFields, type FieldValidationError } from "@/lib/api/validationErrors";

// Error branching for every address write: kind/status/code only.
// Every string here is frontend-owned — Problem.detail/title and
// ValidationError.msg are never returned, so they can never be rendered.

export interface AddressWriteErrorDescription {
  formMessage: string | null;
  fieldErrors: FieldValidationError[];
  notFound?: boolean;
  limitReached?: boolean;
}

export const ADDRESS_FORM_FIELDS = [
  "label",
  "recipient_name",
  "phone",
  "governorate",
  "city",
  "area",
  "street",
  "landmark_notes",
  "is_default",
] as const;

// The backend's own domain validation reports `type: "value_error"` with
// no useful reason, so each field gets its own specific copy for it.
const VALUE_ERROR_MESSAGES: Readonly<Record<string, string>> = {
  label: "Enter a valid label.",
  recipient_name: "Enter a valid recipient name.",
  phone: "Enter a Lebanese phone number, e.g. 03 123 456 or +961 71 123 456.",
  governorate: "Choose a governorate.",
  city: "Enter a valid city.",
  area: "Enter a valid area, or leave it empty.",
  street: "Enter a valid street, or leave it empty.",
  landmark_notes: "Enter valid landmark notes.",
};

export const ADDRESS_MESSAGES = {
  generic: "Something went wrong. Please try again.",
  validation: "Some details weren't accepted. Check the highlighted fields and try again.",
  limit: "Your address book is full. Delete an address before adding a new one.",
  verifyEmail: "Verify your email to add or change saved addresses.",
  csrf: "Unable to verify your session. Please refresh the page and try again.",
  notFound: "This address no longer exists. Your address book has been refreshed.",
  authRequired: "Your session has expired. Please log in again.",
} as const;

function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value;
}

const KNOWN_FIELDS = new Set<string>(ADDRESS_FORM_FIELDS);

export function describeAddressWriteError(error: unknown): AddressWriteErrorDescription {
  const none: FieldValidationError[] = [];
  if (!isApiError(error)) {
    return { formMessage: ADDRESS_MESSAGES.generic, fieldErrors: none };
  }
  if (error.kind === "csrf") {
    return { formMessage: ADDRESS_MESSAGES.csrf, fieldErrors: none };
  }
  if (error.kind !== "http") {
    return { formMessage: ADDRESS_MESSAGES.generic, fieldErrors: none };
  }

  if (error.status === 422 && error.code === "ADDRESS_LIMIT_REACHED") {
    return { formMessage: ADDRESS_MESSAGES.limit, fieldErrors: none, limitReached: true };
  }
  if (error.status === 422 && error.code === "VALIDATION_ERROR") {
    // The shared mapper owns loc -> field and the type -> safe-copy table;
    // only value_error gets a more specific, per-field message here.
    const fieldErrors = (error.errors ?? []).flatMap((raw) => {
      const [mapped] = mapValidationErrorsToFields([raw]);
      if (!mapped || !KNOWN_FIELDS.has(mapped.field)) {
        return [];
      }
      const specific = raw.type === "value_error" ? VALUE_ERROR_MESSAGES[mapped.field] : undefined;
      return [{ field: mapped.field, message: specific ?? mapped.message }];
    });
    return { formMessage: ADDRESS_MESSAGES.validation, fieldErrors };
  }
  if (error.status === 403 && error.code === "EMAIL_VERIFICATION_REQUIRED") {
    return { formMessage: ADDRESS_MESSAGES.verifyEmail, fieldErrors: none };
  }
  if (error.status === 403 && error.code === "CSRF_INVALID") {
    return { formMessage: ADDRESS_MESSAGES.csrf, fieldErrors: none };
  }
  if (error.status === 404 && error.code === "NOT_FOUND") {
    return { formMessage: ADDRESS_MESSAGES.notFound, fieldErrors: none, notFound: true };
  }
  if (error.status === 401 && error.code === "AUTH_REQUIRED") {
    return { formMessage: ADDRESS_MESSAGES.authRequired, fieldErrors: none };
  }
  return { formMessage: ADDRESS_MESSAGES.generic, fieldErrors: none };
}
