"use client";

import { useState } from "react";
import { Icon } from "@/components/ui/Icon";

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
//
// Batch 3 — Stitch product gallery (COMPONENT-SPECS §24, PAGE-SPECS S4): a
// square main image (4:3 from 768px) on the lavender container with
// object-cover — a real <img>, never a CSS background, so Stitch's tiling
// defect cannot occur — and a thumbnail grid with the selected one ringed in
// primary. No hover zoom: Stitch's zoom was hover-only (unreachable by
// keyboard/touch) and is not existing behaviour. One image shows no
// thumbnail strip (nothing to choose); no image shows a placeholder.
export function ProductImageGallery({ images }: ProductImageGalleryProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);

  if (images.length === 0) {
    return (
      <div className="flex aspect-square w-full flex-col items-center justify-center gap-3 rounded-card border border-outline-variant/30 bg-surface-container-low text-on-surface-variant tablet:aspect-[4/3]">
        <Icon name="image" className="h-12 w-12 text-outline" />
        <span className="font-label text-label-caps uppercase">No image available</span>
      </div>
    );
  }

  const activeImage = images[Math.min(selectedIndex, images.length - 1)]!;

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-hidden rounded-card border border-outline-variant/30 bg-surface-container-low shadow-sm">
        {/* Plain <img>, not next/image: the URL format itself IS confirmed
            (B4 — opaque, ready-to-use root-relative paths), but the actual
            HOST serving `/media` differs per environment (missing locally
            until the dev proxy workaround, nginx in prod) and isn't
            statically knowable here, so next/image's remote-pattern
            allowlist can't be configured — same gap as FVS-012's admin
            ImageGallery and ProductCard. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          data-testid="product-gallery-main-image"
          src={activeImage.src}
          alt={activeImage.alt}
          className="aspect-square w-full object-cover tablet:aspect-[4/3]"
        />
      </div>
      {images.length > 1 && (
        <div className="grid grid-cols-4 gap-3 sm:grid-cols-5 tablet:gap-4">
          {images.map((image, index) => {
            const isSelected = index === selectedIndex;
            return (
              <button
                key={image.id}
                type="button"
                aria-current={isSelected ? "true" : undefined}
                onClick={() => setSelectedIndex(index)}
                className={`aspect-square overflow-hidden rounded-control bg-surface-container-low transition-colors duration-200 ${
                  isSelected
                    ? "border-2 border-primary"
                    : "border border-outline-variant/30 opacity-80 hover:border-primary hover:opacity-100"
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- same media-host gap as above */}
                <img src={image.src} alt={image.alt} className="h-full w-full object-cover" />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
