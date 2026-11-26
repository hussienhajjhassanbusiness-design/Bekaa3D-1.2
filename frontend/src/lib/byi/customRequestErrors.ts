import type { ApiError } from "@/lib/api/ApiError";
import { describeGuestSubmissionFailure } from "@/lib/forms/guestSubmissionErrors";

// BYI-specific refusals on top of the shared guest-form mapper (backend
// 2dfb27b engagement/api/custom_requests.py):
//   422 UPLOAD_REJECTED   loc [body, attachments(, i)] - count, size, type
//                         or an undecodable image; nothing stored
//   422 MALWARE_DETECTED  loc [body, attachments, i]   - nothing stored
//   503 SERVICE_UNAVAILABLE - the captcha verifier OR the malware scanner;
//                         the same code for both, so one neutral message
// The server's reason text (detail / msg) is never shown; the file is named
// from the visitor's own selection by the reported index.

export const BYI_FIELD_LABELS: Readonly<Record<string, string>> = {
  name: "Name",
  email: "Email",
  phone: "Phone",
  project_title: "Project title",
  description: "Description",
  preferred_material: "Preferred material",
  preferred_colour: "Preferred colour",
  dimensions: "Dimensions",
};

export const BYI_ERROR_COPY = {
  uploadRejected: "An image couldn't be accepted. Use up to 5 JPEG, PNG or WebP images, each under 10 MB.",
  uploadRejectedFile: (name: string) =>
    `“${name}” couldn't be accepted. Use a JPEG, PNG or WebP image under 10 MB. Nothing was submitted.`,
  malware: "An image was rejected by the security scan. Nothing was submitted.",
  malwareFile: (name: string) => `“${name}” was rejected by the security scan. Remove it and try again. Nothing was submitted.`,
  unavailable: "We can't accept requests right now. Please try again in a few minutes.",
} as const;

function attachmentIndex(error: ApiError): number | null {
  for (const item of error.errors ?? []) {
    if (item.loc[1] === "attachments" && typeof item.loc[2] === "number") return item.loc[2];
  }
  return null;
}

export function describeCustomRequestFailure(error: unknown, attachments: readonly File[]): string {
  const e = error as ApiError;
  if (typeof e === "object" && e !== null && e.kind === "http") {
    if (e.status === 503) return BYI_ERROR_COPY.unavailable;
    if (e.code === "UPLOAD_REJECTED" || e.code === "MALWARE_DETECTED") {
      const index = attachmentIndex(e);
      const file = index !== null ? attachments[index] : undefined;
      if (e.code === "MALWARE_DETECTED") return file ? BYI_ERROR_COPY.malwareFile(file.name) : BYI_ERROR_COPY.malware;
      return file ? BYI_ERROR_COPY.uploadRejectedFile(file.name) : BYI_ERROR_COPY.uploadRejected;
    }
  }
  return describeGuestSubmissionFailure(error, BYI_FIELD_LABELS).message;
}
