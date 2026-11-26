import type { ReactNode, Ref } from "react";
import Link from "next/link";
import { Icon, type IconName } from "@/components/ui/Icon";

// #BATCH4-AUTH-SHELL
//
// Presentation for every authentication surface (redesign Batch 4,
// COMPONENT-SPECS §38 "Auth Card", PAGE-SPECS A1–A3). It owns layout only:
// the blueprint canvas, the card, the brand line, the heading block and the
// footer strip. It never owns form state, requests, validation, captcha or
// any auth decision — every page keeps those exactly where they were and
// passes its existing markup in as children.
//
// Deviations from Stitch (recorded in BEKAA3D-REDESIGN-PLAN Batch 4):
// - One canvas texture, the green 40px blueprint grid (DESIGN-SYSTEM §12.20),
//   instead of the per-page dot / line / SVG patterns.
// - One card radius (16px panel) and width family: 440px (login, and the
//   448px forgot-password card unified to it) and 640px (registration).
// - The storefront Header and Footer stay on auth pages
//   (BEKAA3D-ROUTE-MIGRATION "Auth" shell), so no fixed logo / copyright.
// - Below 640px the card is full-bleed (no side border, radius or shadow)
//   with a 16px inner gutter, so the 300px captcha frame fits at 320px.
// - No decorative status bar ("servers online", "AES-256"): those are
//   unverifiable claims (Batch 4 copy rule).

export type AuthStatusTone = "success" | "error" | "warning" | "info";

export interface AuthCardProps {
  title: string;
  // Pages that move focus to the heading after a state change (success,
  // dead link) pass a ref; the heading is then a programmatic focus target.
  titleRef?: Ref<HTMLHeadingElement>;
  eyebrow?: string;
  description?: ReactNode;
  // A state glyph above the title (COMPONENT-SPECS §48 success circle,
  // extended to the error / warning states of the derived pages).
  status?: { icon: IconName; tone: AuthStatusTone };
  align?: "center" | "start";
  width?: "default" | "wide";
  // The split "Bekaa" + "3D" wordmark at the top of the card (§38 login).
  showBrand?: boolean;
  // A hairline under the heading block (§38 register).
  headerDivider?: boolean;
  footer?: ReactNode;
  children?: ReactNode;
  className?: string;
}

const STATUS_TONE_CLASSES: Record<AuthStatusTone, string> = {
  success: "bg-secondary-container text-on-secondary-container",
  error: "bg-error-container text-error",
  warning: "bg-warning-container text-on-warning-container",
  info: "bg-surface-container text-primary",
};

export function AuthCard({
  title,
  titleRef,
  eyebrow,
  description,
  status,
  align = "center",
  width = "default",
  showBrand = false,
  headerDivider = false,
  footer,
  children,
  className,
}: AuthCardProps) {
  const isCentered = align === "center";

  return (
    <div
      className={`w-full ${width === "wide" ? "max-w-auth-wide" : "max-w-auth"} border-y border-outline-variant/30 bg-surface-container-lowest sm:rounded-panel sm:border sm:shadow-xl ${className ?? ""}`}
    >
      <div
        className={`px-4 pt-8 pb-6 sm:px-10 sm:pt-10 ${isCentered ? "text-center" : "text-left"} ${
          headerDivider ? "mb-8 border-b border-outline-variant/20" : ""
        }`}
      >
        {showBrand && (
          // Decorative: the header already carries the brand link, and the
          // heading names the page. Hidden from assistive tech to avoid
          // announcing "Bekaa3D" twice before the heading.
          <p aria-hidden="true" className="mb-4 font-headline text-headline-md font-extrabold tracking-tight">
            <span className="text-on-surface">Bekaa</span>
            <span className="text-primary">3D</span>
          </p>
        )}
        {status && (
          <div
            className={`mb-5 flex h-16 w-16 items-center justify-center rounded-full ${STATUS_TONE_CLASSES[status.tone]} ${
              isCentered ? "mx-auto" : ""
            }`}
          >
            <Icon name={status.icon} className="h-8 w-8" />
          </div>
        )}
        {eyebrow && <p className="mb-3 font-label text-label-caps uppercase text-primary">{eyebrow}</p>}
        <h1
          ref={titleRef}
          tabIndex={titleRef ? -1 : undefined}
          className={`font-headline text-headline-lg text-on-surface break-words ${titleRef ? "rounded-control" : ""}`}
        >
          {title}
        </h1>
        {description && (
          <div className={`mt-3 text-body-md text-on-surface-variant ${isCentered ? "mx-auto max-w-sm" : ""}`}>
            {description}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-6 px-4 pb-8 sm:px-10 sm:pb-10">{children}</div>

      {footer && (
        <div className="border-t border-outline-variant/30 bg-surface-container-low px-4 py-5 text-center text-body-md text-on-surface-variant sm:rounded-b-panel sm:px-10">
          {footer}
        </div>
      )}
    </div>
  );
}

// The full auth page: blueprint canvas + centred card, inside the existing
// storefront chrome (main landmark comes from AppLayout).
export function AuthShell(props: AuthCardProps) {
  return (
    <div className="flex justify-center bg-blueprint py-6 sm:px-margin-mobile sm:py-12 lg:py-16">
      <AuthCard {...props} />
    </div>
  );
}

// Shared link treatments inside auth cards.
export const AUTH_INLINE_LINK_CLASSES =
  "font-medium text-primary underline underline-offset-4 decoration-primary/40 transition-colors duration-200 hover:decoration-primary";

// "Back to log in" (§38 forgot): mono caps primary link with a back arrow,
// above a hairline divider. 44px target.
export function AuthBackToLogin() {
  return (
    <div className="border-t border-outline-variant/30 pt-6 text-center">
      <Link
        href="/login"
        className="inline-flex min-h-11 items-center gap-2 rounded-control px-2 font-label text-label-caps uppercase text-primary transition-colors duration-200 hover:bg-primary/5"
      >
        <Icon name="arrow-back" className="h-4 w-4" />
        Back to log in
      </Link>
    </div>
  );
}
