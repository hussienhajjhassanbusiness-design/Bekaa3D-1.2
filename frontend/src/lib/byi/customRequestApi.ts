import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";

// #FVS-BYI (phase 6B-2) — Bring Your Idea: POST /api/v1/custom-requests
// (backend 2dfb27b engagement/api/custom_requests.py, custom_request_schemas.py,
// domain/custom_request.py; VS-034, FR-15, ADR-030). Public: guests submit,
// no session or CSRF. multipart/form-data:
//   name               required, 1-100
//   email              required, an email address (<= 254)
//   phone              REQUIRED, <= 32, phone-shaped (+, digits, space ( ) . -, >= 6 digits)
//   project_title      required, 1-200
//   description        required, 1-5000, line breaks allowed
//   preferred_material optional, <= 100 (free text, not a catalogue id)
//   preferred_colour   optional, <= 100 (free text)
//   dimensions         optional, <= 200 (free text)
//   captcha_token      required, Turnstile
//   attachments        0-5 files, each 1 byte to 10 MB; JPEG, PNG or WebP,
//                      the type read from the CONTENT (not the name). Each is
//                      malware-scanned and re-encoded synchronously before
//                      the 201: there is no pending/scanning state.
// The whole body must be <= 5 x 10 MB + 64 KB and carry a Content-Length
// (the browser sets it for a FormData body).
// 201 -> {id, created_at}. No attachment URLs; the submitter has no status
// page (the lead is admin-only, BR-111). Limits/h: 20 attempts, then 5 per
// IP and 5 per email.
export const BYI_LIMITS = {
  name: 100,
  email: 254,
  phone: 32,
  projectTitle: 200,
  description: 5000,
  preference: 100,
  dimensions: 200,
  maxAttachments: 5,
  maxAttachmentBytes: 10 * 1024 * 1024,
} as const;

export const BYI_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;

// A 50 MB upload over a slow line needs far more than the 10 s default.
const SUBMIT_TIMEOUT_MS = 180_000;

export interface CustomRequestFormValues {
  name: string;
  email: string;
  phone: string;
  project_title: string;
  description: string;
  preferred_material: string;
  preferred_colour: string;
  dimensions: string;
}

export interface CustomRequestReceiptDTO {
  id: string;
  created_at: string;
}

const OPTIONAL_FIELDS = ["preferred_material", "preferred_colour", "dimensions"] as const;

// Exact multipart body: trimmed text parts, blank optionals omitted, one
// `attachments` part per file in selection order (the server reports a
// rejected file by that index).
export function toCustomRequestFormData(
  values: CustomRequestFormValues,
  attachments: readonly File[],
  captchaToken: string
): FormData {
  const form = new FormData();
  form.append("name", values.name.trim());
  form.append("email", values.email.trim());
  form.append("phone", values.phone.trim());
  form.append("project_title", values.project_title.trim());
  form.append("description", values.description.trim());
  for (const field of OPTIONAL_FIELDS) {
    const value = values[field].trim();
    if (value) form.append(field, value);
  }
  form.append("captcha_token", captchaToken);
  for (const file of attachments) form.append("attachments", file, file.name);
  return form;
}

export interface SubmitCustomRequestInput {
  values: CustomRequestFormValues;
  attachments: readonly File[];
  captchaToken: string;
}

export function submitCustomRequest({ values, attachments, captchaToken }: SubmitCustomRequestInput): Promise<CustomRequestReceiptDTO> {
  return apiClient.postForm<CustomRequestReceiptDTO>(
    "/api/v1/custom-requests",
    toCustomRequestFormData(values, attachments, captchaToken),
    { timeoutMs: SUBMIT_TIMEOUT_MS }
  );
}

// Never auto-retried: each attempt spends a single-use captcha token.
export function useSubmitCustomRequest() {
  return useMutation({ mutationFn: submitCustomRequest, retry: false });
}
