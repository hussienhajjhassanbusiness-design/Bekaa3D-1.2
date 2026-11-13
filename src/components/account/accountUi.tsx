import Link from "next/link";
import { useId, type ReactNode } from "react";
import { Button } from "@/components/forms/Button";
import { Icon, type IconName } from "@/components/ui/Icon";

// #ACCOUNT-UI (redesign Batch 7)
//
// Presentation-only building blocks shared by the account commerce pages
// (orders, order detail, offers, wishlist), so each page does not fork its
// own card, section, skeleton or load-state markup. They own no data,
// state or business logic: callers pass already-safe copy and handlers.
//
// Stitch card language (COMPONENT-SPECS §11/§43, DESIGN-SYSTEM §6): white
// surface, 12px radius, outline-variant/30 hairline, shadow-sm.

export const ACCOUNT_CARD = "rounded-card border border-outline-variant/30 bg-surface-container-lowest shadow-sm";

// Mono uppercase label (COMPONENT-SPECS §27 label role) for <dt>s and
// small captions. CSS-only uppercase: the text keeps its source casing.
export const ACCOUNT_TERM = "font-label text-label-sm uppercase tracking-widest text-on-surface-variant";

// Text link in the primary ink with a 44px practical target.
export const ACCOUNT_TEXT_LINK =
  "inline-flex min-h-11 items-center gap-1 font-semibold text-primary underline decoration-primary/40 underline-offset-4 hover:decoration-primary";

export interface AccountSectionProps {
  title: string;
  children: ReactNode;
  // Optional decorative glyph beside the heading.
  icon?: IconName;
  // Optional element on the heading row's right (e.g. a status badge).
  aside?: ReactNode;
  // Lavender summary surface (Stitch §35) instead of the white card.
  tinted?: boolean;
}

// A titled section card. The h2 names the region (aria-labelledby), so the
// heading outline and the landmark name are the same visible text.
export function AccountSection({ title, children, icon, aside, tinted = false }: AccountSectionProps) {
  const headingId = useId();
  const surface = tinted ? "rounded-panel border border-outline-variant/30 bg-surface-container-low" : ACCOUNT_CARD;
  return (
    <section aria-labelledby={headingId} className={`${surface} flex min-w-0 flex-col gap-4 p-5 tablet:p-6`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id={headingId} className="flex min-w-0 items-center gap-2 font-headline text-headline-md text-on-surface">
          {icon && <Icon name={icon} className="h-5 w-5 shrink-0 text-primary" />}
          <span className="break-words">{title}</span>
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

// Card-shaped loading placeholder. One polite status with a text label;
// the shapes are decorative and stop pulsing under reduced motion.
export function AccountListSkeleton({ label, rows = 3 }: { label: string; rows?: number }) {
  return (
    <div role="status" className={`${ACCOUNT_CARD} divide-y divide-outline-variant/30`}>
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} aria-hidden="true" className="flex flex-col gap-3 p-5 tablet:p-6">
          <div className="flex items-center justify-between gap-4">
            <div className="h-4 w-40 max-w-[50%] animate-pulse rounded bg-surface-container-high motion-reduce:animate-none" />
            <div className="h-6 w-24 animate-pulse rounded-full bg-surface-container-high motion-reduce:animate-none" />
          </div>
          <div className="h-4 w-2/3 animate-pulse rounded bg-surface-container-high motion-reduce:animate-none" />
        </div>
      ))}
    </div>
  );
}

// A load failure with its retry action. role="alert" is on the card so the
// message and the action are announced together.
export function AccountErrorCard({
  message,
  onRetry,
  retryLabel = "Try again",
}: {
  message: string;
  onRetry: () => void;
  retryLabel?: string;
}) {
  return (
    <div role="alert" className={`${ACCOUNT_CARD} flex flex-col items-start gap-4 p-5 tablet:p-6`}>
      <div className="flex items-start gap-3 rounded-card border border-error/20 bg-error-container p-4 text-on-error-container">
        <Icon name="error" className="h-5 w-5 shrink-0 text-error" />
        <p className="min-w-0 break-words text-body-md">{message}</p>
      </div>
      <Button type="button" variant="outline" onClick={onRetry}>
        {retryLabel}
      </Button>
    </div>
  );
}

// The signed-out-mid-session state: a warning card with the sign-in link
// (returnTo preserved by the caller's href).
export function AccountSessionCard({
  message,
  href,
  linkLabel = "Sign in",
}: {
  message: string;
  href: string;
  linkLabel?: string;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-card border border-warning-outline bg-warning-container p-5 text-on-warning-container tablet:p-6"
    >
      <div className="flex items-start gap-3">
        <Icon name="lock" className="h-5 w-5 shrink-0" />
        <p className="min-w-0 break-words text-body-md">{message}</p>
      </div>
      <Link href={href} className={ACCOUNT_TEXT_LINK}>
        {linkLabel}
      </Link>
    </div>
  );
}

// "Back to …" navigation above a detail page's header.
export function AccountBackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="mb-4 inline-flex min-h-11 items-center gap-2 rounded-control font-label text-label-caps uppercase text-primary hover:underline"
    >
      <Icon name="arrow-back" className="h-4 w-4" />
      {children}
    </Link>
  );
}

// A small "label above value" fact for summary strips and fact grids.
export function AccountFact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className={ACCOUNT_TERM}>{term}</dt>
      <dd className="mt-1 break-words text-body-md text-on-surface">{children}</dd>
    </div>
  );
}

// A thumbnail tile with the decorative fallback glyph (Batch 6 cart
// convention) when there is no image. Always decorative (alt="").
export function AccountThumb({
  src,
  fallbackIcon,
  className = "h-16 w-16",
}: {
  src: string | null | undefined;
  fallbackIcon: IconName;
  className?: string;
}) {
  return (
    <div
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center overflow-hidden rounded-control border border-outline-variant/30 bg-surface-container-low text-on-surface-variant ${className}`}
    >
      {src ? (
        // Plain <img>, matching CartLineItem/ProductCard: the media host is
        // not configured for next/image.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="" className="h-full w-full object-cover" />
      ) : (
        <Icon name={fallbackIcon} className="h-6 w-6" strokeWidth={1.5} />
      )}
    </div>
  );
}
