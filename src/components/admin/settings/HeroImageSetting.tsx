"use client";

import { useEffect, useId, useMemo, useRef, type ChangeEvent } from "react";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { HERO_IMAGE_REQUIREMENTS } from "@/lib/home/heroImageApi";

export interface HeroImageSettingProps {
  // The saved image's URL; null = none set (the default brand visual shows);
  // undefined = still loading.
  currentUrl: string | null | undefined;
  // The current image couldn't be read; a new one can still be uploaded.
  loadError?: boolean;
  // Chosen but not saved yet: the page's single "Save changes" uploads it.
  pendingFile: File | null;
  // "Restore default" chosen but not saved yet: Save clears the setting.
  restorePending?: boolean;
  onSelect: (file: File) => void;
  onRestoreDefault: () => void;
  // Back to the saved image: drops a chosen file or a pending restore.
  onClearSelection: () => void;
  error?: string;
}

// Homepage → Hero image, on Store Settings. The preview is the same square,
// covering image as the homepage hero (HeroVisual), so what the admin sees
// is what customers get.
export function HeroImageSetting({
  currentUrl,
  loadError = false,
  pendingFile,
  restorePending = false,
  onSelect,
  onRestoreDefault,
  onClearSelection,
  error,
}: HeroImageSettingProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const hintId = useId();
  // A local object URL for the chosen file, released when it changes or the
  // control unmounts. Nothing leaves the browser until Save.
  const previewUrl = useMemo(() => (pendingFile ? URL.createObjectURL(pendingFile) : null), [pendingFile]);
  useEffect(() => {
    if (!previewUrl) return;
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset so choosing the same file again still fires a change.
    event.target.value = "";
    if (file) onSelect(file);
  }

  const showsDefault = restorePending || (!previewUrl && currentUrl === null && !loadError);
  const shownUrl = restorePending ? null : (previewUrl ?? currentUrl ?? null);
  const caption = restorePending
    ? "Default brand visual — not saved yet"
    : previewUrl
      ? "New image — not saved yet"
      : currentUrl
        ? "Current image"
        : loadError
          ? "Couldn't load the current image."
          : currentUrl === null
            ? "Default brand visual (no image uploaded)"
            : "Loading current image…";

  return (
    <div className="flex flex-col gap-5 tablet:flex-row tablet:items-start">
      <figure className="w-full max-w-60 shrink-0">
        <div
          data-testid="hero-image-preview"
          className="bg-blueprint relative flex aspect-square items-center justify-center overflow-hidden rounded-panel border border-outline-variant/30 shadow-sm"
        >
          {shownUrl ? (
            // eslint-disable-next-line @next/next/no-img-element -- a local object URL or backend media URL
            <img
              src={shownUrl}
              alt={previewUrl ? "Preview of the new hero image" : "Current hero image"}
              className="absolute inset-0 h-full w-full object-cover"
            />
          ) : (
            showsDefault && (
              // eslint-disable-next-line @next/next/no-img-element -- static local brand asset
              <img
                src="/brand/bekaa3d-mark.png"
                alt="Default brand visual"
                width={129}
                height={144}
                className="w-2/5"
              />
            )
          )}
        </div>
        <figcaption className="mt-2 font-label text-label-sm text-on-surface-variant">{caption}</figcaption>
      </figure>

      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div>
          <h3 id={titleId} className="font-headline text-title-sm text-on-surface">
            Hero image
          </h3>
          <p id={hintId} className="mt-1 text-body-md text-on-surface-variant">
            The large image on the right of the homepage hero, shown from tablet width up. {HERO_IMAGE_REQUIREMENTS}
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="sr-only"
          tabIndex={-1}
          aria-labelledby={titleId}
          aria-describedby={hintId}
          onChange={handleChange}
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={() => inputRef.current?.click()} aria-describedby={hintId}>
            {currentUrl || pendingFile ? "Replace image" : "Choose image"}
          </Button>
          {!restorePending && (currentUrl || pendingFile) && (
            <Button variant="ghost" onClick={onRestoreDefault}>
              Restore default
            </Button>
          )}
          {((pendingFile && currentUrl) || restorePending) && (
            <Button variant="ghost" onClick={onClearSelection}>
              Keep current image
            </Button>
          )}
        </div>
        {pendingFile && (
          <p className="break-all text-body-md text-on-surface-variant">
            Selected: {pendingFile.name}. Save changes to publish it.
          </p>
        )}
        {restorePending && (
          <p className="text-body-md text-on-surface-variant">
            The homepage will show the default Bekaa3D visual. Save changes to apply it.
          </p>
        )}
        {error && <Alert variant="error" message={error} />}
      </div>
    </div>
  );
}
