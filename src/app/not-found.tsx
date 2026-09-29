import Link from "next/link";
import { AppLayout } from "@/components/layout/AppLayout";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";

// Next.js App Router's global catch-all 404 — handles every unmatched URL.
// Not extracted into a separate NotFoundPage component: there is no known
// reuse case for this content yet (YAGNI).
export default function NotFound() {
  return (
    <AppLayout header={<Header />} footer={<Footer />}>
      <h1 className="text-h1 font-bold text-text-primary">404 — Page not found</h1>
      <p className="text-body text-text-secondary">
        The page you&rsquo;re looking for doesn&rsquo;t exist or may have been moved.
      </p>
      <Link href="/" className="text-text-link underline">
        Back to home
      </Link>
    </AppLayout>
  );
}
