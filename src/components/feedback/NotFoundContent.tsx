import Link from "next/link";

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
    <>
      <h1 className="text-h1 font-bold text-text-primary">404 — Page not found</h1>
      <p className="text-body text-text-secondary">
        The page you&rsquo;re looking for doesn&rsquo;t exist or may have been moved.
      </p>
      <Link href="/" className="text-text-link underline">
        Back to home
      </Link>
    </>
  );
}
