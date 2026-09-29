import Link from "next/link";

// Next.js App Router's global catch-all 404 — handles every unmatched URL.
// Not extracted into a separate NotFoundPage component: there is no known
// reuse case for this content yet (YAGNI). The AppLayout/Header/Footer
// shell is owned by the root layout (FVS001-T14) — this file owns only its
// own not-found content.
export default function NotFound() {
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
