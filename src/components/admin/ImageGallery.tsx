"use client";

import { useState } from "react";
import { Button } from "@/components/forms/Button";
import { TextField } from "@/components/forms/TextField";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";

// Frontend-normalized gallery presentation model — NOT a claim about any
// backend field name. The real product-image response shape (id, URL
// representation, order field, cover field) is still
// NEEDS BACKEND CONFIRMATION (FVS-012-IMPLEMENTATION-PLAN.md §1). A
// future API adapter maps whatever the backend returns onto this shape.
export interface GalleryImageModel {
  id: string;
  src: string;
  // Display/aria label — always non-empty (falls back to the product
  // name when there is no alt text yet).
  accessibleLabel: string;
  // The real, editable alt-text value — undefined/"" when unset,
  // distinct from `accessibleLabel`'s display fallback so editing never
  // silently "saves" the fallback text as if the admin had typed it.
  altText?: string;
  isCover: boolean;
}

export interface ImageGalleryProps {
  images: readonly GalleryImageModel[];
  onReorder: (nextIds: string[]) => void;
  onSetCover: (imageId: string) => void;
  // Resolves `true` only when the delete actually succeeded — the dialog
  // then closes and drops its target. Anything else (false/void/a
  // rejection) keeps the dialog open on the same image for retry; the
  // caller owns surfacing the safe error message.
  onDelete: (imageId: string) => Promise<boolean> | boolean | void;
  // Optional — a caller with no alt-text-editing concept simply omits
  // it and no such control renders (e.g. a hypothetical read-only
  // gallery view).
  onUpdateAltText?: (imageId: string, nextAltText: string) => void;
  isDeleting?: boolean;
  isUpdatingAltText?: boolean;
}

// #FVS012-UPLOAD
//
// Reorder is explicit "Move up"/"Move down" buttons, not pointer drag —
// recorded decision (FVS-012-IMPLEMENTATION-PLAN.md §5/T04): drag adds
// real complexity without changing what is safe to ship now, these
// buttons already give every user (mouse, keyboard, touch) a working
// reorder path with no device-detection branching, and the
// `onReorder(nextIds)` callback shape is already exactly what a later
// pointer-drag enhancement would also call — adding drag later needs no
// redesign here. Order is array order only; the backend's own order
// field is a future adapter's concern, never claimed by this component.
//
// Cover state renders as visible text ("Cover"), never icon/color
// alone. Delete reuses the existing ConfirmDialog (FVS-007/009) — no new
// modal. Neither Set Cover nor Delete is treated as locally authoritative:
// this component only exposes the presentation seam (onSetCover/
// onDelete); the real mutation and the server's own race/conflict
// handling are a future adapter's job (T06, blocked).
export function ImageGallery({
  images,
  onReorder,
  onSetCover,
  onDelete,
  onUpdateAltText,
  isDeleting = false,
  isUpdatingAltText = false,
}: ImageGalleryProps) {
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  // A target that is no longer in the gallery (e.g. removed by the
  // post-delete refetch) is never actionable — the dialog can't stay open
  // pointing at an image that no longer exists.
  const activeDeleteTargetId =
    deleteTargetId !== null && images.some((image) => image.id === deleteTargetId) ? deleteTargetId : null;

  async function confirmDelete() {
    const targetId = activeDeleteTargetId;
    if (!targetId) {
      return;
    }
    let succeeded = false;
    try {
      succeeded = (await onDelete(targetId)) === true;
    } catch {
      succeeded = false;
    }
    if (succeeded) {
      setDeleteTargetId((current) => (current === targetId ? null : current));
    }
  }

  function move(index: number, direction: -1 | 1) {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= images.length) {
      return;
    }
    const nextIds = images.map((image) => image.id);
    const [moved] = nextIds.splice(index, 1);
    nextIds.splice(targetIndex, 0, moved!);
    onReorder(nextIds);
  }

  return (
    <>
      <ul>
      {images.map((image, index) => (
        <li key={image.id} className="flex items-center gap-3 border-b border-border-default py-3">
          {/* Plain <img>, not next/image: the real image host/URL format
              is still an open gap (FRONTEND-VERTICAL-SLICE-PLAN.md §17's
              "Image/asset URL format" item) — next/image's remote-pattern
              allowlist can't be configured safely until that's confirmed. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={image.src} alt={image.accessibleLabel} className="h-16 w-16 rounded-sm object-cover" />
          <span className="text-body text-text-primary">{image.accessibleLabel}</span>
          {image.isCover && (
            <span className="rounded-pill bg-brand-dark-green/15 px-2 py-0.5 text-caption font-semibold text-brand-dark-green">
              Cover
            </span>
          )}
          {onUpdateAltText && (
            <AltTextEditor
              label={`Alt text (image ${index + 1})`}
              altText={image.altText ?? ""}
              onSave={(next) => onUpdateAltText(image.id, next)}
              isSaving={isUpdatingAltText}
            />
          )}
          <div className="ml-auto flex items-center gap-2">
            <Button type="button" onClick={() => move(index, -1)} disabled={index === 0}>
              Move up
            </Button>
            <Button type="button" onClick={() => move(index, 1)} disabled={index === images.length - 1}>
              Move down
            </Button>
            {!image.isCover && (
              <Button type="button" onClick={() => onSetCover(image.id)}>
                Set as cover
              </Button>
            )}
            <Button type="button" onClick={() => setDeleteTargetId(image.id)}>
              Delete
            </Button>
          </div>
        </li>
      ))}
      </ul>

      <ConfirmDialog
        open={activeDeleteTargetId !== null}
        title="Delete image"
        description="This image will be removed from the gallery."
        confirmLabel="Delete"
        isDestructive
        isConfirming={isDeleting}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteTargetId(null)}
      />
    </>
  );
}

interface AltTextEditorProps {
  label: string;
  altText: string;
  onSave: (next: string) => void;
  isSaving: boolean;
}

// Owns only the ephemeral draft of its own row (same pattern as
// SettingRow's draft value) — the real pending/persisted alt text lives
// in the caller's own mutation hook, not here. `label` is per-row and
// distinguishing (e.g. "Alt text (image 2)") — a shared "Alt text" label
// repeated identically across every row in a multi-image gallery would be
// ambiguous for a screen-reader user with no visual grouping cue.
function AltTextEditor({ label, altText, onSave, isSaving }: AltTextEditorProps) {
  const [draft, setDraft] = useState(altText);

  return (
    <div className="flex items-center gap-2">
      <TextField label={label} value={draft} onChange={(event) => setDraft(event.target.value)} />
      <Button type="button" isLoading={isSaving} onClick={() => onSave(draft)}>
        Save alt text
      </Button>
    </div>
  );
}
