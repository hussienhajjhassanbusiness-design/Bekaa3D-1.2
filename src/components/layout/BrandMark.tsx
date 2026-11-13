// #BATCH2-BRAND-MARK
//
// The real Bekaa3D logo glyph (public/brand/bekaa3d-mark.png: the hexagon
// mark cropped from docs/assets' logo, white made transparent, colours
// untouched — never recoloured to the UI green) beside the Stitch standard
// wordmark (DESIGN-SYSTEM §12.6 variant 2: Hanken Grotesk 20px, weight 800).
//
// Shared by the header (as a home link) and the footer (plain text). The
// image is decorative (empty alt): the adjacent text is the name, so the
// header link's accessible name stays exactly "Bekaa3D".
export interface BrandMarkProps {
  // "primary" in the header (Stitch standard), "on-surface" in the footer.
  tone?: "primary" | "on-surface";
}

export function BrandMark({ tone = "primary" }: BrandMarkProps) {
  return (
    <span className="inline-flex items-center gap-2.5">
      {/* eslint-disable-next-line @next/next/no-img-element -- a 19 KB static
          PNG at a fixed size: next/image's optimiser adds nothing here. */}
      <img src="/brand/bekaa3d-mark.png" alt="" width={129} height={144} className="h-9 w-auto shrink-0" />
      <span
        className={`font-headline text-headline-md font-extrabold leading-none tracking-tight ${
          tone === "primary" ? "text-primary" : "text-on-surface"
        }`}
      >
        Bekaa3D
      </span>
    </span>
  );
}
