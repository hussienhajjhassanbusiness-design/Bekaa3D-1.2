import type { ValidationErrorItem } from "./ApiError";

// Phase 2 auth/account batch — error-contract correction: "Validation
// errors use errors[].loc/msg/type... For form-field mapping: drop loc[0]
// ("body"/"query"/"path") and map the remaining path... Do not surface
// backend diagnostic detail/msg directly to the user... Use friendly
// frontend-owned messages." This module owns both rules: the loc->field
// mapping, and a small type->safe-message table. The backend's own `msg`
// is read only to select a branch during development/debugging — it is
// never assigned to the returned `message`.

export interface FieldValidationError {
  field: string;
  message: string;
}

const SAFE_MESSAGES_BY_TYPE: Readonly<Record<string, string>> = {
  missing: "This field is required.",
  string_too_short: "This value is too short.",
  string_too_long: "This value is too long.",
  extra_forbidden: "This field isn't accepted by the server.",
  value_error: "Enter a valid value.",
  json_invalid: "The request could not be read.",
};

const GENERIC_FIELD_MESSAGE = "This value is invalid.";

function safeMessageForType(type: string): string {
  return SAFE_MESSAGES_BY_TYPE[type] ?? GENERIC_FIELD_MESSAGE;
}

// loc[0] is always the request-part segment ("body"/"query"/"path") per
// the confirmed contract — dropped unconditionally, never inspected. A
// loc with nothing left after that (e.g. ["body"] alone, a whole-body
// error with no specific field) maps to the empty-string field, which
// callers treat as a form-level error rather than attaching it to one
// input.
export function mapValidationErrorsToFields(
  errors: readonly ValidationErrorItem[] | undefined
): FieldValidationError[] {
  if (!errors) {
    return [];
  }
  return errors.map((error) => ({
    field: error.loc.slice(1).join("."),
    message: safeMessageForType(error.type),
  }));
}
