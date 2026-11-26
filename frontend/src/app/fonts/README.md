# Vendored fonts

Loaded by `src/app/fonts.ts` through `next/font/local`. Nothing is requested
from Google Fonts at build time or at runtime.

| File | Family | Axes | Subset | Source |
|---|---|---|---|---|
| `HankenGrotesk-latin-var.woff2` | Hanken Grotesk | wght 100–900 | Latin | Google Fonts (fonts.gstatic.com, v12) |
| `Inter-latin-var.woff2` | Inter | wght 100–900 | Latin | Google Fonts (fonts.gstatic.com, v20) |
| `JetBrainsMono-latin-var.woff2` | JetBrains Mono | wght 100–800 | Latin | Google Fonts (fonts.gstatic.com, v24) |

All three families are licensed under the SIL Open Font License 1.1
(https://openfontlicense.org), which permits bundling and redistribution
with the application.

Only the Latin subset is vendored, which covers the app's current English
UI. If a locale needs Latin Extended, Cyrillic or another script, add that
subset's woff2 here and list it in the `src` array in `fonts.ts`.
