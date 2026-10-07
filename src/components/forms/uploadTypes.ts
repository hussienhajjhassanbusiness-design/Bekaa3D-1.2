// #ARCHITECTURE-UPLOAD-ADAPTER
//
// Frontend-normalized upload model — NOT a backend DTO. `FileUploader`
// owns only local queue UX (selection, local precheck, progress, cancel,
// retry); a future endpoint-specific adapter (product images, STL
// assets, BYI attachments — all contract-gated, see
// FVS-012-IMPLEMENTATION-PLAN.md §1) owns the real HTTP/multipart
// request and maps whatever the server actually returns onto this
// model's terms via the injected `UploadDriver` seam (see
// FileUploader.tsx).
//
// Deliberately local-only states: "queued" | "uploading" | "failed" |
// "done". No "accepted"/"scanning"/"quarantined"/"stored" — those would
// be claims about backend vocabulary this plan has not confirmed exists
// (FRONTEND-VERTICAL-SLICE-PLAN.md §11 anticipates a future "scanning"
// polling phase as a frontend architecture *intention*, but VS-012's own
// backend text never confirms whether the upload response is
// synchronous accept/reject or async-with-a-pending-scan-state — that
// stays a recorded, contract-gated discrepancy, not a guess baked into
// this model). "done" means only "the injected driver resolved success"
// — it is the driver's job, once the real contract lands, to decide
// what counts as success; this component has no independent opinion.
export type UploadStatus = "queued" | "uploading" | "failed" | "done";

export interface UploadQueueItem {
  id: string;
  file: File;
  status: UploadStatus;
  progress: number;
  rejectionReason?: string;
}

// Client-side pre-check configuration ONLY — never populated with
// hardcoded numbers/types here. The real limits are
// NEEDS BACKEND CONFIRMATION per upload surface (product images here;
// STL assets/BYI attachments reuse this same component with their own
// future config). An absent field means "no local limit enforced for
// that dimension" — it does NOT mean "no backend limit exists."
export interface UploadValidationConfig {
  allowedMimeTypes?: readonly string[];
  maxBytes?: number;
  maxFiles?: number;
}

export interface UploadPrecheckRejection {
  file: File;
  reason: string;
}

export interface UploadPrecheckResult {
  accepted: File[];
  rejected: UploadPrecheckRejection[];
}

// #SECURITY-UPLOAD-PRECHECK
//
// UX-only fast feedback. The backend remains the sole authority on real
// file-content inspection, MIME/type acceptance, size/count enforcement,
// and malware scanning — this function never claims to be a security
// boundary, and a file that passes this check can still be rejected by
// the server. `File.type` is the browser's own best-guess MIME sniff
// (from the OS, not content inspection) and is used here only as a
// convenience pre-check, never as proof of real content type.
export function precheckFiles(
  files: readonly File[],
  config: UploadValidationConfig,
  currentAcceptedCount: number
): UploadPrecheckResult {
  const accepted: File[] = [];
  const rejected: UploadPrecheckRejection[] = [];
  let acceptedCount = currentAcceptedCount;

  for (const file of files) {
    if (config.allowedMimeTypes && !config.allowedMimeTypes.includes(file.type)) {
      rejected.push({ file, reason: `"${file.name}" isn't a supported file type.` });
      continue;
    }
    if (config.maxBytes !== undefined && file.size > config.maxBytes) {
      rejected.push({ file, reason: `"${file.name}" is too large.` });
      continue;
    }
    if (config.maxFiles !== undefined && acceptedCount >= config.maxFiles) {
      rejected.push({ file, reason: `"${file.name}" exceeds the maximum number of files.` });
      continue;
    }
    accepted.push(file);
    acceptedCount += 1;
  }

  return { accepted, rejected };
}
