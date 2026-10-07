"use client";

import { useId, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Button } from "@/components/forms/Button";
import { precheckFiles, type UploadPrecheckRejection, type UploadQueueItem, type UploadValidationConfig } from "./uploadTypes";

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
  driver: UploadDriver;
  multiple?: boolean;
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
export function FileUploader({ label, config, driver, multiple = false }: FileUploaderProps) {
  const inputId = useId();
  const [queue, setQueue] = useState<UploadQueueItem[]>([]);
  const [localRejections, setLocalRejections] = useState<readonly UploadPrecheckRejection[]>([]);
  const [announcement, setAnnouncement] = useState("");
  const controllersRef = useRef(new Map<string, AbortController>());
  const cancelledIdsRef = useRef(new Set<string>());

  function announce(text: string) {
    setAnnouncement(text);
  }

  function updateItem(id: string, patch: Partial<UploadQueueItem>) {
    setQueue((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }

  async function startUpload(item: UploadQueueItem) {
    const controller = new AbortController();
    controllersRef.current.set(item.id, controller);
    updateItem(item.id, { status: "uploading", progress: 0 });
    announce(`${item.file.name}: uploading`);

    try {
      const result = await driver(item.file, {
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

    for (const file of accepted) {
      const item: UploadQueueItem = { id: createLocalId(), file, status: "queued", progress: 0 };
      setQueue((prev) => [...prev, item]);
      void startUpload(item);
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
    if (item) {
      cancelledIdsRef.current.delete(id);
      void startUpload(item);
    }
  }

  return (
    <div data-testid="file-dropzone" onDrop={handleDrop} onDragOver={(event) => event.preventDefault()}>
      <label htmlFor={inputId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
        {label}
      </label>
      <input id={inputId} type="file" multiple={multiple} onChange={handleInputChange} className="mt-1" />

      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>

      {localRejections.map((rejection, index) => (
        <p key={index} role="alert" className="mt-2 text-caption text-danger">
          {rejection.reason}
        </p>
      ))}

      {queue.length > 0 && (
        <ul className="mt-2">
          {queue.map((item) => (
            <li key={item.id} className="flex items-center gap-2 py-1">
              <span className="text-body text-text-primary">{item.file.name}</span>

              {item.status === "uploading" && (
                <progress value={item.progress} max={100} aria-label={`Uploading ${item.file.name}`} />
              )}

              {item.status === "done" && <span className="text-caption text-success">Uploaded</span>}

              {item.status === "failed" && (
                <p role="alert" className="text-caption text-danger">
                  {item.rejectionReason ?? GENERIC_FAILURE_MESSAGE}
                </p>
              )}

              {(item.status === "queued" || item.status === "uploading") && (
                <Button type="button" onClick={() => handleCancel(item.id)}>
                  Cancel
                </Button>
              )}

              {item.status === "failed" && (
                <Button type="button" onClick={() => handleRetry(item.id)}>
                  Retry
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
