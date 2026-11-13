import { Icon } from "@/components/ui/Icon";

export interface RatingSummaryProps {
  averageRating: number;
  reviewCount: number;
  // "sm": product card row. "md": product detail, with the word "reviews".
  size?: "sm" | "md";
}

const RATING_FORMAT = new Intl.NumberFormat("en", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

// #SHARED-RATING-SUMMARY (redesign Batch 3; extracted from Batch 2's
// ProductCard, now also on the product page)
//
// Real `average_rating` / `review_count` only. Renders nothing at zero
// reviews: a permanent "(0)" would look like a broken or fake widget.
// Spoken once as a sentence; the compact visual is aria-hidden. The star
// uses the warning token (amber-600, 3.2:1) — Stitch's amber-400 is 2.1:1,
// below the 3:1 graphics minimum (DESIGN-SYSTEM §12.12 deviation).
export function RatingSummary({ averageRating, reviewCount, size = "sm" }: RatingSummaryProps) {
  if (reviewCount <= 0) return null;

  const average = RATING_FORMAT.format(averageRating);
  const noun = reviewCount === 1 ? "review" : "reviews";

  return (
    <span className={`font-body text-on-surface-variant ${size === "md" ? "text-body-md" : "text-sm"}`}>
      <span className="sr-only">{`Rated ${average} out of 5 from ${reviewCount} ${noun}`}</span>
      <span aria-hidden="true" className="inline-flex items-center gap-1">
        <Icon name="star" fill="currentColor" strokeWidth={1} className={`text-warning ${size === "md" ? "h-5 w-5" : "h-4 w-4"}`} />
        <span className="font-semibold text-on-surface">{average}</span>
        <span>{size === "md" ? `(${reviewCount} ${noun})` : `(${reviewCount})`}</span>
      </span>
    </span>
  );
}
