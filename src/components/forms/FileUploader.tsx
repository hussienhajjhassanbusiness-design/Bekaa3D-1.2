"use client";

import { useId, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Button } from "@/components/forms/Button";
import {
  FIELD_ERROR_CLASSES,
  FIELD_HINT_CLASSES,
  FIELD_LABEL_CLASSES,
  FieldErrorIcon,
} from "@/components/forms/fieldStyles";
import { Icon } from "@/components/ui/Icon";
import {
  precheckFiles,
  type UploadPrecheckRejection,
  type UploadQueueItem,
  type UploadValidationConfig,
} from "./uploadTypes";

export interface UploadDriverHandlers {
  onProgress: (percent: number) => void;
  signal: AbortSignal;
}

export type UploadDriverResult = { ok: true } | { ok: false; reason: string };

// Transport seam only — no real HTTP, no XHR/fetch, no multipart
// implementation lives in this file. A future endpoint-specific adapter
// (product images here; STL assets/BYI attachments reuse this same
// component) supplies the real driver once its contract is confirmed
// (FVS-012-IMPLEMENTATION-PLAN.md §1). FileUploader never calls this
// itself except through the injected prop, so a presentational unit
// test can inject a fake driver and assert zero real network activity.
export type UploadDriver = (file: File, handlers: UploadDriverHandlers) => Promise<UploadDriverResult>;

export interface FileUploaderProps {
  label: string;
  config: UploadValidationConfig;
  // Omit entirely for deferred-selection mode: accepted files are held
  // in memory only (status "selected"), never uploaded, and reported to
  // the parent via `onSelectionChange` — e.g. BYI attachments, bundled
  // into one later request by a parent form
  // (FVS-015-IMPLEMENTATION-PLAN.md §0/§5). Supply it for immediate-
  // upload mode — e.g. admin product images — where each accepted file
  // starts uploading right away through the injected transport.
  driver?: UploadDriver;
  multiple?: boolean;
  // Called with the current list of selected/queued File objects
  // whenever it changes (add or remove). Primarily meaningful in
  // deferred mode, where it is the only way a parent learns what's
  // selected; harmless and unused in immediate mode.
  onSelectionChange?: (files: File[]) => void;
  // Phase 6B — optional native file-picker filter (e.g. "image/jpeg,image/png")
  // and a visible hint. A picker filter is a convenience only; `config` and
  // ultimately the server stay the real checks.
  accept?: string;
  hint?: string;
}

const GENERIC_FAILURE_MESSAGE = "Upload failed. Please try again.";
const CANCELLED_MESSAGE = "Upload cancelled.";

function createLocalId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

// #FVS012-UPLOAD
//
// Shared, product-agnostic upload UX — must never learn about "product",
// "image", "STL", "BYI", or any specific endpoint. Every later upload
// surface configures this same component with its own `config` and
// `driver` rather than a bespoke uploader
// (FRONTEND-VERTICAL-SLICE-PLAN.md §11). T03 (a separate transport/
// controller seam) is deliberately absorbed here: the injected
// `UploadDriver` already is that seam, and a second wrapper would add no
// real separation of concerns.
//
// "done" means only "the injected driver resolved { ok: true }" — never
// rendered as a backend-specific claim; see uploadTypes.ts's own note on
// why "accepted"/"scanning"/"stored" are not modeled here.
//
// Transport-independent by design: the selection/dropzone/precheck/list
// UX below is identical in both modes. `driver` present → immediate
// upload starts the moment a file is accepted. `driver` absent →
// deferred selection: accepted files sit in memory as "selected" and
// are reported via `onSelectionChange`; nothing is ever sent.
export function FileUploader({
  label,
  config,
  driver,
  multiple = false,
  onSelectionChange,
  accept,
  hint,
}: FileUploaderProps) {
  const inputId = useId();
  const hintId = useId();
  const [queue, setQueue] = useState<UploadQueueItem[]>([]);
  const [localRejections, setLocalRejections] = useState<readonly UploadPrecheckRejection[]>([]);
  const [announcement, setAnnouncement] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const controllersRef = useRef(new Map<string, AbortController>());
  const cancelledIdsRef = useRef(new Set<string>());

  function announce(text: string) {
    setAnnouncement(text);
  }

  function updateItem(id: string, patch: Partial<UploadQueueItem>) {
    setQueue((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }

  async function startUpload(item: UploadQueueItem, activeDriver: UploadDriver) {
    const controller = new AbortController();
    controllersRef.current.set(item.id, controller);
    updateItem(item.id, { status: "uploading", progress: 0 });
    announce(`${item.file.name}: uploading`);

    try {
      const result = await activeDriver(item.file, {
        onProgress: (percent) => updateItem(item.id, { progress: percent }),
        signal: controller.signal,
      });

      if (cancelledIdsRef.current.has(item.id)) {
        return;
      }

      if (result.ok) {
        updateItem(item.id, { status: "done", progress: 100 });
        announce(`${item.file.name}: uploaded`);
      } else {
        updateItem(item.id, { status: "failed", rejectionReason: result.reason });
        announce(`${item.file.name}: failed`);
      }
    } catch {
      // A thrown/rejected driver carries no safe, confirmed message —
      // never render the raw exception. A cancelled upload gets its own
      // clear reason; anything else gets the generic fallback.
      const reason = cancelledIdsRef.current.has(item.id) ? CANCELLED_MESSAGE : GENERIC_FAILURE_MESSAGE;
      updateItem(item.id, { status: "failed", rejectionReason: reason });
      announce(`${item.file.name}: failed`);
    } finally {
      controllersRef.current.delete(item.id);
      cancelledIdsRef.current.delete(item.id);
    }
  }

  function handleFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    if (files.length === 0) {
      return;
    }

    const { accepted, rejected } = precheckFiles(files, config, queue.length);
    setLocalRejections(rejected);

    if (accepted.length === 0) {
      return;
    }

    const newItems: UploadQueueItem[] = accepted.map((file) => ({
      id: createLocalId(),
      file,
      status: driver ? "queued" : "selected",
      progress: 0,
    }));
    const nextQueue = [...queue, ...newItems];
    setQueue(nextQueue);
    onSelectionChange?.(nextQueue.map((item) => item.file));

    if (driver) {
      const activeDriver = driver;
      for (const item of newItems) {
        void startUpload(item, activeDriver);
      }
    } else {
      announce(newItems.length === 1 ? `${newItems[0]!.file.name} added.` : `${newItems.length} files added.`);
    }
  }

  function handleRemove(id: string) {
    const removed = queue.find((item) => item.id === id);
    const nextQueue = queue.filter((item) => item.id !== id);
    setQueue(nextQueue);
    onSelectionChange?.(nextQueue.map((item) => item.file));
    if (removed) {
      announce(`${removed.file.name} removed.`);
    }
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    if (event.target.files) {
      handleFiles(event.target.files);
    }
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (event.dataTransfer?.files) {
      handleFiles(event.dataTransfer.files);
    }
  }

  function handleCancel(id: string) {
    cancelledIdsRef.current.add(id);
    controllersRef.current.get(id)?.abort();
  }

  function handleRetry(id: string) {
    const item = queue.find((candidate) => candidate.id === id);
    // Retry only ever renders for status "failed", which only occurs in
    // immediate mode — `driver` is guaranteed present by construction,
    // but TypeScript can't see that across the render/callback boundary.
    if (item && driver) {
      cancelledIdsRef.current.delete(id);
      void startUpload(item, driver);
    }
  }

  const atLimit = config.maxFiles !== undefined && queue.length >= config.maxFiles;

  return (
    <div>
      <label htmlFor={inputId} className={FIELD_LABEL_CLASSES}>
        {label}
      </label>
      {hint && (
        <p id={hintId} className={FIELD_HINT_CLASSES}>
          {hint}
        </p>
      )}
      {/* Stitch §30 dropzone. The real control is the native file input
          (visually hidden but focusable, so keyboard and screen-reader users
          get the platform picker); clicking anywhere in the zone opens it and
          dropping files is an extra, never the only, way in. */}
      <div
        data-testid="file-dropzone"
        data-dragging={isDragging || undefined}
        onClick={(event) => {
          if (event.target !== inputRef.current) inputRef.current?.click();
        }}
        onDrop={(event) => {
          setIsDragging(false);
          handleDrop(event);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          if (!isDragging) setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        className={`group relative mt-2 flex cursor-pointer flex-col items-center justify-center rounded-card border-2 border-dashed px-4 py-8 text-center transition-colors duration-200 ease-standard focus-within:border-primary focus-within:shadow-focus-ring tablet:px-10 tablet:py-10 motion-reduce:transition-none ${
          isDragging
            ? "border-primary bg-primary/5"
            : "border-outline bg-surface-container-low/50 hover:border-primary hover:bg-primary/5"
        }`}
      >
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          multiple={multiple}
          accept={accept}
          aria-describedby={hint ? hintId : undefined}
          onChange={handleInputChange}
          className="sr-only"
        />
        <span className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary transition-transform duration-200 ease-standard group-hover:scale-110 motion-reduce:transition-none motion-reduce:group-hover:scale-100">
          <Icon name="upload-file" className="h-8 w-8" />
        </span>
        <span aria-hidden="true" className="mt-4 font-headline text-title-sm text-on-surface">
          Drop files here or <span className="text-primary underline underline-offset-2">browse</span>
        </span>
        {config.maxFiles !== undefined && (
          <span aria-hidden="true" className="mt-2 font-label text-label-sm uppercase text-on-surface-variant">
            {queue.length} / {config.maxFiles} {atLimit ? "· limit reached" : "selected"}
          </span>
        )}
      </div>

      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>

      {localRejections.map((rejection, index) => (
        <p key={index} role="alert" className={FIELD_ERROR_CLASSES}>
          <FieldErrorIcon />
          <span className="min-w-0 break-words">{rejection.reason}</span>
        </p>
      ))}

      {queue.length > 0 && (
        <ul className="mt-4 flex flex-col gap-2">
          {queue.map((item) => (
            <li
              key={item.id}
              className="flex flex-wrap items-center gap-3 rounded-control border border-outline-variant bg-surface-container-lowest p-3"
            >
              <Icon name="image" className="h-5 w-5 text-primary" />
              <div className="min-w-0 flex-1">
                <p className="break-all font-body text-body-md font-semibold text-on-surface">{item.file.name}</p>
                <p className="font-label text-label-sm uppercase text-on-surface-variant">
                  {formatFileSize(item.file.size)}
                </p>

                {item.status === "uploading" && (
                  <progress
                    value={item.progress}
                    max={100}
                    aria-label={`Uploading ${item.file.name}`}
                    className="mt-2 h-1 w-full overflow-hidden rounded-full accent-primary"
                  />
                )}

                {item.status === "done" && (
                  <p className="mt-1 flex items-center gap-1 text-xs text-primary">
                    <Icon name="check-circle" className="h-4 w-4" />
                    Uploaded
                  </p>
                )}

                {item.status === "failed" && (
                  <p role="alert" className={FIELD_ERROR_CLASSES}>
                    <FieldErrorIcon />
                    <span className="min-w-0 break-words">{item.rejectionReason ?? GENERIC_FAILURE_MESSAGE}</span>
                  </p>
                )}
              </div>

              {(item.status === "queued" || item.status === "uploading") && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="min-h-11"
                  onClick={() => handleCancel(item.id)}
                >
                  Cancel
                </Button>
              )}

              {item.status === "failed" && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="min-h-11"
                  onClick={() => handleRetry(item.id)}
                >
                  Retry
                </Button>
              )}

              {item.status === "selected" && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="min-h-11 text-error enabled:hover:bg-error/5"
                  aria-label={`Remove ${item.file.name}`}
                  onClick={() => handleRemove(item.id)}
                >
                  <Icon name="close" className="h-4 w-4" />
                  Remove
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
