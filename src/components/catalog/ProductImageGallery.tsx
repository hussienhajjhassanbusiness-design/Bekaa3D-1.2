"use client";

import { useState } from "react";

// Frontend-normalized public gallery model — NOT a claim about any
// backend field name (FVS-014-IMPLEMENTATION-PLAN.md §1). Deliberately
// simpler than FVS-012's admin `GalleryImageModel`: no `isCover` flag,
// since the public viewer only needs an ordered list and treats the
// first image as the initial/main one — a future adapter's job to put
// the cover image first, not this component's concern.
export interface ProductGalleryImage {
  id: string;
  src: string;
  alt: string;
}

export interface ProductImageGalleryProps {
  images: readonly ProductGalleryImage[];
}

// #FVS014-PRODUCT-GALLERY
//
// PUBLIC viewer only — deliberately a separate component from FVS-012's
// admin `ImageGallery`, never shared, because the two interaction
// models genuinely diverge (admin: reorder/cover/delete a mutable list;
// public: select which already-ordered image is the main one). Forcing
// one shared component now would mean either leaking admin actions onto
// the public page or building an abstraction with no second real
// pressure case yet — see FVS-014-IMPLEMENTATION-PLAN.md §5/T03 for the
// full extraction-vs-separate-component decision record.
//
// Selection is local, ephemeral UI state only (no persistence). No
// carousel library, no auto-play — the thumbnail strip gets native
// horizontal scroll via `overflow-x-auto` for mobile, not a JS-driven
// swipe gesture.
export function ProductImageGallery({ images }: ProductImageGalleryProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);

  if (images.length === 0) {
    return null;
  }

  const activeImage = images[Math.min(selectedIndex, images.length - 1)]!;

  return (
    <div>
      {/* Plain <img>, not next/image: the URL format itself IS confirmed
          (B4 — opaque, ready-to-use root-relative paths), but the actual
          HOST serving `/media` differs per environment (missing locally
          until the dev proxy workaround, nginx in prod) and isn't
          statically knowable here, so next/image's remote-pattern
          allowlist can't be configured — same gap as FVS-012's admin
          ImageGallery and ProductCard. */}
      <img
        data-testid="product-gallery-main-image"
        src={activeImage.src}
        alt={activeImage.alt}
        className="w-full rounded-md object-cover"
      />
      <div className="mt-2 flex gap-2 overflow-x-auto">
        {images.map((image, index) => (
          <button
            key={image.id}
            type="button"
            aria-current={index === selectedIndex ? "true" : undefined}
            onClick={() => setSelectedIndex(index)}
            className={`shrink-0 rounded-sm border-2 ${
              index === selectedIndex ? "border-brand-dark-green" : "border-border-default"
            }`}
          >
            <img src={image.src} alt={image.alt} className="h-16 w-16 object-cover" />
          </button>
        ))}
      </div>
    </div>
  );
}
