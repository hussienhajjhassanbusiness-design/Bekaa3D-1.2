import Link from "next/link";
import { BrandMark } from "./BrandMark";

interface FooterColumn {
  heading: string;
  links: readonly { href: string; label: string }[];
}

// Only routes actually mounted today. Account destinations are plain links:
// /account and /cart own their own protection (an anonymous visitor is sent
// to /login with a safe returnTo), so the footer needs no auth state.
const COLUMNS: readonly FooterColumn[] = [
  {
    heading: "Shop",
    links: [
      { href: "/shop", label: "Shop" },
      { href: "/bring-your-idea", label: "Bring your idea" },
    ],
  },
  {
    heading: "Company",
    links: [
      { href: "/about", label: "About" },
      { href: "/contact", label: "Contact" },
    ],
  },
  {
    heading: "Your account",
    links: [
      { href: "/account", label: "My account" },
      { href: "/account/wishlist", label: "Wishlist" },
      { href: "/cart", label: "Cart" },
    ],
  },
];

// Content for AppLayout's <footer> landmark — not a second <footer>
// element.
//
// Stitch footer, recommended canonical (DESIGN-SYSTEM §12.8, COMPONENT-SPECS
// §6): surface-container-low, outline-variant top border, 1440px content,
// brand column + link columns with mono caps headings, Inter 16px links
// (on-surface-variant → primary), and a bottom bar with the copyright.
// Deliberately absent (no real source exists): newsletter (no endpoint),
// social circles (no profiles), payment logos, and Stitch's placeholder
// Documentation / Privacy / Terms links (no such pages).
export function Footer() {
  const year = new Date().getFullYear();

  return (
    <div className="border-t border-outline-variant bg-surface-container-low">
      <div className="mx-auto max-w-content px-margin-mobile pb-24 pt-16 tablet:px-8 tablet:pb-28 tablet:pt-24 desktop:px-margin-desktop">
        <div className="grid grid-cols-1 gap-12 desktop:grid-cols-4 desktop:gap-gutter">
          <div className="flex flex-col gap-6">
            <BrandMark tone="on-surface" />
            {/* Copy condensed from the approved /about text. */}
            <p className="max-w-sm font-body text-body-md text-on-surface-variant">
              3D-printed goods made to order, and STL files for makers who print their own.
            </p>
          </div>

          <nav aria-label="Footer" className="desktop:col-span-3">
            <div className="grid grid-cols-2 gap-x-gutter gap-y-10 tablet:grid-cols-3">
              {COLUMNS.map((column) => (
                <div key={column.heading}>
                  <h2 className="mb-6 font-label text-label-caps uppercase text-on-surface">{column.heading}</h2>
                  <ul className="flex flex-col gap-4">
                    {column.links.map((link) => (
                      <li key={link.href}>
                        <Link
                          href={link.href}
                          className="rounded-badge font-body text-body-md text-on-surface-variant transition-colors duration-200 hover:text-primary"
                        >
                          {link.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </nav>
        </div>

        <div className="mt-16 flex flex-col gap-3 border-t border-outline-variant/30 pt-8 tablet:mt-20 tablet:flex-row tablet:items-center tablet:justify-between">
          <p className="font-body text-sm text-on-surface-variant">© {year} Bekaa3D. All rights reserved.</p>
          <p className="font-label text-label-caps uppercase text-on-surface-variant">Engineered Grade 3D Solutions</p>
        </div>
      </div>
    </div>
  );
}
