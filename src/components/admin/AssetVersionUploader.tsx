"use client";

import { FileUploader } from "@/components/forms/FileUploader";
import type { UploadValidationConfig } from "@/components/forms/uploadTypes";

export interface AssetVersionUploaderProps {
  config: UploadValidationConfig;
  onSelectionChange: (files: File[]) => void;
}

// #FVS018-ASSET-VERSION-UPLOADER
//
// Reuses the shared FileUploader (FVS-012) in its deferred-selection
// mode (no `driver`) — not a second picker/dropzone/precheck
// implementation. VS-016's bundle-create endpoint and request body are
// still NEEDS BACKEND CONFIRMATION (FVS-018-IMPLEMENTATION-PLAN.md
// §1), so nothing uploads yet; selected files are reported to the
// parent via `onSelectionChange`, and a future "Create version" action
// seam submits the bundle once the real endpoint is known. No MIME/
// size/count limit is hardcoded — `config` must come from a confirmed
// backend/product source, never inferred from this slice's "STL" name
// (the backend may allow more formats than a raw .stl file).
export function AssetVersionUploader({ config, onSelectionChange }: AssetVersionUploaderProps) {
  return <FileUploader label="New asset version files" config={config} multiple onSelectionChange={onSelectionChange} />;
}
