import localFont from "next/font/local";

// Stitch type system (docs/design-handoff/DESIGN-TOKENS.md §2.1):
//   Hanken Grotesk -> headings / display      (--font-headline, --font-display)
//   Inter          -> body text               (--font-body, --font-sans)
//   JetBrains Mono -> labels, buttons, table-style uppercase utility text (--font-label)
//
// Self-hosted with next/font/local from vendored variable woff2 files
// (Latin subset, SIL Open Font License 1.1 — see ./fonts/README.md). Nothing
// is fetched from Google at build time or at runtime, so offline CI builds
// work and the production CSP (`font-src 'self'`) is satisfied. Each loader
// only exposes a CSS variable; globals.css composes it with the documented
// fallback stack, and next/font adds size-adjusted local fallbacks to limit
// layout shift while the files load.
export const hankenGrotesk = localFont({
  src: "./fonts/HankenGrotesk-latin-var.woff2",
  weight: "100 900",
  style: "normal",
  display: "swap",
  variable: "--font-hanken-grotesk-face",
});

export const inter = localFont({
  src: "./fonts/Inter-latin-var.woff2",
  weight: "100 900",
  style: "normal",
  display: "swap",
  variable: "--font-inter-face",
});

export const jetBrainsMono = localFont({
  src: "./fonts/JetBrainsMono-latin-var.woff2",
  weight: "100 800",
  style: "normal",
  display: "swap",
  variable: "--font-jetbrains-mono-face",
});

export const fontVariablesClassName = `${hankenGrotesk.variable} ${inter.variable} ${jetBrainsMono.variable}`;
