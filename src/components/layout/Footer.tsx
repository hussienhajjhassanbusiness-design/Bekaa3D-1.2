import Link from "next/link";

// Content for AppLayout's <footer> landmark — not a second <footer>
// element. Only links to routes actually mounted (/shop, /about and, from
// phase 6B, /bring-your-idea and /contact) — no legal/social links, since no such page exists.
export function Footer() {
  return (
    <div className="border-t border-border-default bg-surface-subtle px-4 py-6 tablet:px-6 desktop:px-8">
      <div className="flex flex-col items-center gap-3 tablet:flex-row tablet:justify-between">
        <span className="text-body font-semibold text-text-primary">Bekaa3D</span>
        <nav aria-label="Footer">
          <ul className="flex flex-wrap justify-center gap-x-6 gap-y-2">
            <li>
              <Link href="/shop" className="text-caption text-text-secondary hover:text-brand-dark-green">
                Shop
              </Link>
            </li>
            <li>
              <Link href="/about" className="text-caption text-text-secondary hover:text-brand-dark-green">
                About
              </Link>
            </li>
            <li>
              <Link href="/bring-your-idea" className="text-caption text-text-secondary hover:text-brand-dark-green">
                Bring your idea
              </Link>
            </li>
            <li>
              <Link href="/contact" className="text-caption text-text-secondary hover:text-brand-dark-green">
                Contact
              </Link>
            </li>
          </ul>
        </nav>
        <span className="text-caption text-text-secondary">Engineered Grade 3D Solutions</span>
      </div>
    </div>
  );
}
