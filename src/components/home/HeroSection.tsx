import Link from "next/link";
import { buttonLinkClassName } from "@/components/forms/Button";
import { Container } from "@/components/ui/Container";
import { Icon, type IconName } from "@/components/ui/Icon";

export interface HeroCta {
  label: string;
  href: string;
}

export interface HeroSectionProps {
  heading?: string;
  supportingCopy?: string;
  primaryCta?: HeroCta;
  secondaryCta?: HeroCta;
}

// The only approved marketing-copy fragment found anywhere in the
// repository (FVS-022-IMPLEMENTATION-PLAN.md §0) — chosen as the
// default heading so this component satisfies both a real hero
// requirement and e2e/smoke.spec.ts's existing assertion that this
// exact text renders as the home page's heading, without needing to
// touch that spec.
const DEFAULT_HEADING = "Bekaa3D — Engineered Grade 3D Solutions";
const HEADING_SEPARATOR = " — ";

// Facts shown on the decorative brand panel: the two real product types,
// in the same words as the approved Why Choose / About copy. No invented
// statistics or machine status (Stitch's "2,500+ models", "PRINTING 68%").
const PANEL_CHIPS: readonly { icon: IconName; label: string; value: string; position: string }[] = [
  { icon: "deployed-code", label: "Physical prints", value: "Made to order", position: "-right-4 top-8 desktop:-right-6" },
  { icon: "download", label: "STL files", value: "Print it yourself", position: "-left-4 bottom-10 desktop:-left-8" },
];

// #FVS022-HERO-SECTION
//
// Brand-focused, reusable. CTAs are only rendered when explicitly
// supplied with a real href — never a disabled anchor, never a
// default/invented destination.
//
// Batch 3 — Stitch split hero (COMPONENT-SPECS §9, PAGE-SPECS S1): mono
// eyebrow, display H1 whose second half carries the text gradient, lead,
// CTA row (primary + outline), and on the right a decorative brand panel.
// No photograph exists for this slot, so the panel is the real logo mark
// on the blueprint grid with two glass chips — never a Stitch placeholder
// image. The whole visual side and the blurred orbs are aria-hidden.
export function HeroSection({ heading = DEFAULT_HEADING, supportingCopy, primaryCta, secondaryCta }: HeroSectionProps) {
  const separatorIndex = heading.indexOf(HEADING_SEPARATOR);
  const lead = separatorIndex >= 0 ? heading.slice(0, separatorIndex + HEADING_SEPARATOR.length) : null;
  const accent = separatorIndex >= 0 ? heading.slice(separatorIndex + HEADING_SEPARATOR.length) : heading;

  return (
    <section aria-labelledby="hero-heading" className="relative isolate overflow-hidden">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute -bottom-32 -left-24 h-80 w-80 rounded-full bg-secondary-fixed/30 blur-3xl" />
      </div>

      <Container className="grid items-center gap-12 py-16 tablet:py-24 desktop:grid-cols-2 desktop:gap-16 desktop:py-28">
        <div>
          <span className="mb-4 block font-label text-label-caps uppercase tracking-widest text-primary">
            Physical prints · STL files
          </span>
          <h1 id="hero-heading" className="mb-6 font-display text-display text-on-surface">
            {lead}
            <span className={lead ? "text-gradient-primary" : undefined}>{accent}</span>
          </h1>
          {supportingCopy && <p className="mb-8 max-w-lg font-body text-body-lg text-on-surface-variant">{supportingCopy}</p>}
          {(primaryCta || secondaryCta) && (
            <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap">
              {primaryCta && (
                <Link href={primaryCta.href} className={buttonLinkClassName("primary", "lg")}>
                  {primaryCta.label}
                  <Icon name="arrow-forward" className="h-4 w-4" />
                </Link>
              )}
              {secondaryCta && (
                <Link href={secondaryCta.href} className={buttonLinkClassName("secondary", "lg")}>
                  {secondaryCta.label}
                </Link>
              )}
            </div>
          )}
        </div>

        <div aria-hidden="true" className="relative mx-auto hidden w-full max-w-md tablet:block desktop:max-w-none">
          <div className="bg-blueprint relative flex aspect-square items-center justify-center overflow-hidden rounded-panel border border-outline-variant/30 shadow-2xl">
            <div className="absolute inset-12 rounded-full bg-primary/5 blur-2xl" />
            {/* eslint-disable-next-line @next/next/no-img-element -- static local brand asset */}
            <img src="/brand/bekaa3d-mark.png" alt="" width={129} height={144} className="relative w-2/5 drop-shadow-xl" />
          </div>
          {PANEL_CHIPS.map((chip) => (
            <div
              key={chip.label}
              className={`glass-panel absolute ${chip.position} flex items-center gap-3 rounded-card border border-outline-variant/30 p-4 shadow-lg`}
            >
              <span className="flex h-11 w-11 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Icon name={chip.icon} className="h-6 w-6" />
              </span>
              <span className="flex flex-col gap-1">
                <span className="font-label text-label-sm uppercase text-on-surface-variant">{chip.label}</span>
                <span className="font-headline text-title-sm text-on-surface">{chip.value}</span>
              </span>
            </div>
          ))}
        </div>
      </Container>
    </section>
  );
}
