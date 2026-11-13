import Link from "next/link";
import { Container } from "@/components/ui/Container";
import { Icon } from "@/components/ui/Icon";

// Batch 3 — Stitch home "Custom Quote CTA" green panel (COMPONENT-SPECS
// §52), pointed at the app's real equivalents: Bring your idea (the custom
// request form) and Contact. Copy condensed from the approved /bring-your-
// idea intro; no invented service promise. Stitch's WhatsApp button is not
// repeated here — the floating WhatsApp action is already on every page.
export function CustomRequestCtaSection() {
  return (
    <section aria-labelledby="custom-request-heading" className="py-section-mobile tablet:py-section">
      <Container>
        <div className="relative isolate overflow-hidden rounded-banner bg-primary px-6 py-12 text-center text-on-primary tablet:px-12 tablet:py-16 desktop:p-16">
          <div aria-hidden="true" className="absolute -right-24 -top-24 -z-10 h-80 w-80 rounded-full bg-white/10 blur-3xl" />
          <h2 id="custom-request-heading" className="mb-4 font-display text-headline-lg tablet:text-display">
            Have something in mind that isn&apos;t in the shop?
          </h2>
          <p className="mx-auto mb-10 max-w-2xl font-body text-body-lg text-on-primary-container">
            Tell us about it and add a few reference photos or sketches. We&apos;ll get back to you to discuss the details and a
            quote.
          </p>
          <div className="flex flex-col items-stretch justify-center gap-4 sm:flex-row sm:items-center">
            <Link
              href="/bring-your-idea"
              className="inline-flex min-h-13 items-center justify-center gap-2 rounded-control border-2 border-transparent bg-surface-container-lowest px-8 py-3.5 font-label text-label-caps uppercase text-primary shadow-lg transition-colors duration-200 hover:bg-primary-fixed"
            >
              <Icon name="lightbulb" className="h-5 w-5" />
              Bring your idea
            </Link>
            <Link
              href="/contact"
              className="inline-flex min-h-13 items-center justify-center gap-2 rounded-control border-2 border-on-primary/60 px-8 py-3.5 font-label text-label-caps uppercase text-on-primary transition-colors duration-200 hover:border-on-primary hover:bg-on-primary/10"
            >
              <Icon name="mail" className="h-5 w-5" />
              Contact us
            </Link>
          </div>
        </div>
      </Container>
    </section>
  );
}
