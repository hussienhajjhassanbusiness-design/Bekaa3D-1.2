import type { SVGProps } from "react";

// #SHARED-ICON
//
// Local, inline-SVG icon set for the Stitch redesign. Stitch draws icons
// with the Material Symbols Outlined web font from Google's CDN; the app does
// not load it (no remote font dependency, and the production CSP's
// `font-src 'self'` would block it). Each glyph here is a 24×24 outline
// drawing in the same visual weight (≈ Material Symbols wght 400, FILL 0),
// using currentColor so it inherits the surrounding text colour.
//
// Icons are always decorative (`aria-hidden`): the accessible name comes from
// the control's own text or aria-label, never from the icon. Only glyphs a
// shipped component uses are added — extend the map when a batch needs one.
const PATHS = {
  "check-circle": (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12.5l2.75 2.75L16.25 9.5" />
    </>
  ),
  error: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5v5.5" />
      <path d="M12 16.5h.01" />
    </>
  ),
  warning: (
    <>
      <path d="M10.4 4.2a1.85 1.85 0 0 1 3.2 0l7.55 13.1A1.85 1.85 0 0 1 19.55 20H4.45a1.85 1.85 0 0 1-1.6-2.7z" />
      <path d="M12 9.5v4.5" />
      <path d="M12 17h.01" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5.5" />
      <path d="M12 7.5h.01" />
    </>
  ),
  close: <path d="M6 6l12 12M18 6L6 18" />,
  "chevron-down": <path d="M6 9l6 6 6-6" />,
  visibility: (
    <>
      <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  "visibility-off": (
    <>
      <path d="M10.6 5.1A10.4 10.4 0 0 1 12 5c6.4 0 10 7 10 7a17.6 17.6 0 0 1-2.6 3.6" />
      <path d="M6.6 6.6C3.7 8.4 2 12 2 12s3.6 7 10 7a9.7 9.7 0 0 0 5.4-1.6" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
      <path d="M3 3l18 18" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.2-3.2" />
    </>
  ),
} as const;

export type IconName = keyof typeof PATHS;

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "children"> {
  name: IconName;
}

export function Icon({ name, className, strokeWidth = 1.75, ...rest }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className ?? "h-6 w-6"}`}
      data-icon={name}
      {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}
