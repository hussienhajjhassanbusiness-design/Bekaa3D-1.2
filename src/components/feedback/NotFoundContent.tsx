import Link from "next/link";
import { buttonLinkClassName } from "@/components/forms/Button";
import { Icon } from "@/components/ui/Icon";

// #SECURITY-ORDER-IDOR-HIDING
//
// Extracted from src/app/not-found.tsx (its own prior comment said
// extraction was YAGNI — "no known reuse case yet"). FVS-029's
// foreign-order/nonexistent-order case is the second real use case:
// both must render this exact, already-existing not-found experience,
// never a distinct "forbidden" message that would confirm the
// order's existence. The global 404 (src/app/not-found.tsx) and
// OrderDetail's not-found branch both render this component, so
// there is only ever one visible not-found experience, not two
// independently-maintained copies.
export function NotFoundContent() {
  return (
    // Batch 11: the §49 empty-state composition (lavender circle, neutral
    // glyph, one primary action) so the 404 never looks unfinished. It is
    // self-centring, so it reads the same in the storefront, the account
    // shell and the admin content region.
    <div className="mx-auto flex w-full max-w-xl flex-col items-center px-margin-mobile py-16 text-center tablet:py-24">
      <div className="flex h-24 w-24 items-center justify-center rounded-full bg-surface-container">
        <Icon name="search" className="h-12 w-12 text-outline" strokeWidth={1.5} />
      </div>
      <h1 className="mt-6 font-headline text-headline-lg text-on-surface">404 — Page not found</h1>
      <p className="mt-3 text-body-md text-on-surface-variant">
        The page you&rsquo;re looking for doesn&rsquo;t exist or may have been moved.
      </p>
      <Link href="/" className={`mt-8 ${buttonLinkClassName("primary")}`}>
        Back to home
      </Link>
    </div>
  );
}
