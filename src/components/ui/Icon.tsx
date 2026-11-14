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
  // Batch 2 — storefront chrome and product card.
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  "shopping-cart": (
    <>
      <path d="M3 4h2l2.4 10.2a1 1 0 0 0 1 .8h8.9a1 1 0 0 0 1-.8L20 8H6.2" />
      <circle cx="9" cy="19" r="1.4" />
      <circle cx="17" cy="19" r="1.4" />
    </>
  ),
  person: (
    <>
      <circle cx="12" cy="8" r="3.75" />
      <path d="M4.75 19.5c.9-3.4 3.8-5.5 7.25-5.5s6.35 2.1 7.25 5.5" />
    </>
  ),
  login: (
    <>
      <path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4" />
      <path d="M10 8l4 4-4 4" />
      <path d="M14 12H4" />
    </>
  ),
  "arrow-forward": <path d="M5 12h14M13 6l6 6-6 6" />,
  "arrow-back": <path d="M19 12H5M11 6l-6 6 6 6" />,
  lock: (
    <>
      <rect x="5" y="10.5" width="14" height="10" rx="2" />
      <path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3" />
      <path d="M12 14.5v2" />
    </>
  ),
  "content-copy": (
    <>
      <rect x="8.5" y="8.5" width="11" height="12" rx="2" />
      <path d="M15.5 8.5V5.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h2" />
    </>
  ),
  print: (
    <>
      <path d="M7 8.5V3.5h10v5" />
      <rect x="3.5" y="8.5" width="17" height="8" rx="2" />
      <path d="M7 14h10v6.5H7z" />
    </>
  ),
  image: (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <circle cx="9" cy="10" r="1.75" />
      <path d="M20.5 16l-5-5-8.5 8.5" />
    </>
  ),
  star: <path d="M12 3.5l2.6 5.3 5.9.85-4.25 4.15 1 5.85L12 16.9l-5.25 2.75 1-5.85L3.5 9.65l5.9-.85z" />,
  // Batch 3 — home, shop, product detail.
  "filter-list": <path d="M4 7h16M7 12h10M10 17h4" />,
  "chevron-right": <path d="M9 6l6 6-6 6" />,
  add: <path d="M12 5v14M5 12h14" />,
  remove: <path d="M5 12h14" />,
  "deployed-code": (
    <>
      <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" />
      <path d="M4 7.5l8 4.5 8-4.5" />
      <path d="M12 12v9" />
    </>
  ),
  download: (
    <>
      <path d="M12 4v11" />
      <path d="M7 10.5l5 5 5-5" />
      <path d="M5 19.5h14" />
    </>
  ),
  verified: (
    <>
      <path d="M12 3l2.2 1.6 2.7-.1.9 2.6 2.2 1.6-.8 2.6.8 2.6-2.2 1.6-.9 2.6-2.7-.1L12 21l-2.2-1.6-2.7.1-.9-2.6L4 15.3l.8-2.6L4 10.1l2.2-1.6.9-2.6 2.7.1z" />
      <path d="M8.75 12.25l2.25 2.25 4.25-4.5" />
    </>
  ),
  lightbulb: (
    <>
      <path d="M9 17.5h6M10 20.5h4" />
      <path d="M12 3.5a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1.1 2V17.5h5v-1.2c.1-.8.5-1.5 1.1-2A6 6 0 0 0 12 3.5z" />
    </>
  ),
  send: (
    <>
      <path d="M4 19.5L20.5 12 4 4.5l2.5 7.5z" />
      <path d="M6.5 12H12" />
    </>
  ),
  "upload-file": (
    <>
      <path d="M14 3.5H7.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8z" />
      <path d="M14 3.5V8h4.5" />
      <path d="M12 17v-6" />
      <path d="M9.5 13.5L12 11l2.5 2.5" />
    </>
  ),
  mail: (
    <>
      <rect x="3.5" y="5.5" width="17" height="13" rx="2" />
      <path d="M4 7l8 6 8-6" />
    </>
  ),
  category: (
    <>
      <path d="M12 3.5l4.5 7.5h-9z" />
      <circle cx="7.5" cy="16.5" r="3.5" />
      <rect x="13.5" y="13" width="7" height="7" rx="1" />
    </>
  ),
  // Batch 5 — account navigation, address cards, notification rows.
  "shopping-bag": (
    <>
      <path d="M5.5 7.5h13l-1 12.5h-11z" />
      <path d="M9 7.5V6.5a3 3 0 0 1 6 0v1" />
    </>
  ),
  sell: (
    <>
      <path d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7l8.3 8.3a1 1 0 0 1 0 1.4l-7.3 7.3a1 1 0 0 1-1.4 0z" />
      <circle cx="8" cy="8" r="1.25" />
    </>
  ),
  favorite: <path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.2a4.3 4.3 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20z" />,
  "location-on": (
    <>
      <path d="M12 21s-6.5-5.8-6.5-11.2a6.5 6.5 0 0 1 13 0C18.5 15.2 12 21 12 21z" />
      <circle cx="12" cy="9.8" r="2.3" />
    </>
  ),
  notifications: (
    <>
      <path d="M6 16.5v-5.5a6 6 0 0 1 12 0v5.5l1.5 2h-15z" />
      <path d="M10 20.5a2 2 0 0 0 4 0" />
    </>
  ),
  logout: (
    <>
      <path d="M10 4H5.5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1H10" />
      <path d="M15 8l4 4-4 4" />
      <path d="M19 12H9.5" />
    </>
  ),
  edit: (
    <>
      <path d="M4 20h4L19.3 8.7a1.4 1.4 0 0 0 0-2L17.3 4.7a1.4 1.4 0 0 0-2 0L4 16z" />
      <path d="M13.5 6.5l4 4" />
    </>
  ),
  delete: (
    <>
      <path d="M4.5 7h15" />
      <path d="M9.5 7V4.5h5V7" />
      <path d="M6.5 7l1 13h9l1-13" />
      <path d="M10.5 11v5M13.5 11v5" />
    </>
  ),
  call: (
    <path d="M5.5 3.5h3.2l1.8 4.6-2.3 1.4a11 11 0 0 0 6.3 6.3l1.4-2.3 4.6 1.8v3.2a1 1 0 0 1-1 1A16.5 16.5 0 0 1 4.5 4.5a1 1 0 0 1 1-1z" />
  ),
  schedule: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.25 2" />
    </>
  ),
  // Batch 6 — cart and checkout.
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  "local-shipping": (
    <>
      <path d="M3.5 6.5h10v10h-10z" />
      <path d="M13.5 10h4l3 3.5v3h-7" />
      <circle cx="7.5" cy="17.5" r="1.75" />
      <circle cx="17" cy="17.5" r="1.75" />
    </>
  ),
  storefront: (
    <>
      <path d="M4 9.5l1.5-5h13l1.5 5" />
      <path d="M4 9.5a2.7 2.7 0 0 0 5.3 0 2.7 2.7 0 0 0 5.4 0 2.7 2.7 0 0 0 5.3 0" />
      <path d="M5.5 12v8h13v-8" />
      <path d="M10 20v-4.5h4V20" />
    </>
  ),
  payments: (
    <>
      <rect x="3.5" y="6.5" width="17" height="11" rx="1.5" />
      <circle cx="12" cy="12" r="2.25" />
      <path d="M6.5 9.5v.01M17.5 14.5v.01" />
    </>
  ),
  "open-in-new": (
    <>
      <path d="M13.5 4.5h6v6" />
      <path d="M19.5 4.5L11 13" />
      <path d="M17.5 13.5v5a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1h5" />
    </>
  ),
  "receipt-long": (
    <>
      <path d="M6 3.5h12v17l-2-1.25-2 1.25-2-1.25-2 1.25-2-1.25-2 1.25z" />
      <path d="M9 8h6M9 11.5h6M9 15h3.5" />
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
