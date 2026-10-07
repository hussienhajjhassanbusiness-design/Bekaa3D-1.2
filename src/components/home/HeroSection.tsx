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

// #FVS022-HERO-SECTION
//
// Brand-focused, reusable. CTAs are only rendered when explicitly
// supplied with a real href — never a disabled anchor, never a
// default/invented destination, since no currently-valid home-page CTA
// route exists yet (plan §0). No visual/image slot exists in this
// batch — no approved hero asset exists to fill one.
export function HeroSection({ heading = DEFAULT_HEADING, supportingCopy, primaryCta, secondaryCta }: HeroSectionProps) {
  return (
    <section>
      <h1 className="text-h1 font-bold text-text-primary">{heading}</h1>
      {supportingCopy && <p className="text-body text-text-secondary">{supportingCopy}</p>}
      {(primaryCta || secondaryCta) && (
        <div className="mt-4 flex gap-3">
          {primaryCta && (
            <a href={primaryCta.href} className="rounded bg-primary px-4 py-2 text-white">
              {primaryCta.label}
            </a>
          )}
          {secondaryCta && (
            <a href={secondaryCta.href} className="rounded border border-primary px-4 py-2 text-primary">
              {secondaryCta.label}
            </a>
          )}
        </div>
      )}
    </section>
  );
}
