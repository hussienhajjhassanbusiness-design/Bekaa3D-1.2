"use client";

import { useState } from "react";
import { useHeroImage } from "@/lib/home/heroImageApi";

type VisualState = "loading" | "custom" | "default";

// The large square on the hero's right (HeroSection). It shows the image an
// administrator uploaded in Store Settings (GET /api/v1/home/hero-image);
// with none set, or if the backend can't be reached or the image won't load,
// it shows the default brand visual: the logo mark on the blueprint grid.
// While loading it shows the empty panel, so the default never flashes before
// a custom image. The panel's size is fixed (aspect-square) and the image
// covers it, so nothing moves when it arrives. It is decorative: the whole
// visual side is aria-hidden in HeroSection, so the image's alt is empty.
export function HeroVisual() {
  const { data, isPending, isError } = useHeroImage();
  const [failedUrl, setFailedUrl] = useState<string | null>(null);

  const url = data?.url ?? null;
  const state: VisualState = isPending && !isError ? "loading" : url && url !== failedUrl ? "custom" : "default";

  return (
    <div
      data-hero-visual={state}
      className="bg-blueprint relative flex aspect-square items-center justify-center overflow-hidden rounded-panel border border-outline-variant/30 shadow-2xl"
    >
      {state === "custom" && url && (
        // eslint-disable-next-line @next/next/no-img-element -- backend media URL, already re-encoded server-side
        <img
          src={url}
          alt=""
          decoding="async"
          onError={() => setFailedUrl(url)}
          className="absolute inset-0 h-full w-full object-cover"
        />
      )}
      {state === "default" && (
        <>
          <div className="absolute inset-12 rounded-full bg-primary/5 blur-2xl" />
          {/* eslint-disable-next-line @next/next/no-img-element -- static local brand asset */}
          <img
            src="/brand/bekaa3d-mark.png"
            alt=""
            width={129}
            height={144}
            className="relative w-2/5 drop-shadow-xl"
          />
        </>
      )}
    </div>
  );
}
