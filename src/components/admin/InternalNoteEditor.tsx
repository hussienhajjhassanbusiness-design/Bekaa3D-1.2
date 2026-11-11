"use client";

import { useId, useState } from "react";
import { Button } from "@/components/forms/Button";

export interface InternalNoteEditorProps {
  note: string;
  onSave: (note: string) => void;
  isSaving?: boolean;
  errorMessage?: string;
}

// #SECURITY-INTERNAL-NOTE-BOUNDARY
//
// An explicit, screen-reader-read customer-invisibility label, never
// conveyed by styling alone. Local draft state is independent from
// `note` until Save is explicitly clicked — no auto-save, no
// save-on-blur. The note is never persisted to browser storage,
// never logged, never placed in a URL/query key.
//
// Phase 5H: `draft` seeds from `note` only on mount. The admin order page
// (AdminOrderView) remounts it with `key={admin_note}`, so a saved or
// externally changed server note replaces the draft, while an unsaved edit
// survives refetches that leave the note unchanged.
export function InternalNoteEditor({ note, onSave, isSaving = false, errorMessage }: InternalNoteEditorProps) {
  const labelId = useId();
  const [draft, setDraft] = useState(note);

  return (
    <div>
      <label htmlFor={labelId} className="block text-label font-semibold uppercase tracking-label text-danger">
        Internal note — not visible to customers
      </label>
      <textarea
        id={labelId}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        className="mt-1 w-full rounded-sm border border-border-default px-3 py-2 text-body"
      />
      {errorMessage && (
        <p role="alert" className="mt-1 text-caption text-danger">
          {errorMessage}
        </p>
      )}
      <Button type="button" onClick={() => onSave(draft)} disabled={isSaving} isLoading={isSaving} className="mt-2">
        Save
      </Button>
    </div>
  );
}
