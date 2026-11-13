import { WhatsAppGlyph } from "@/components/ui/WhatsAppGlyph";
import { buildWhatsAppHref } from "@/lib/catalog/whatsapp";

export interface FloatingWhatsAppButtonProps {
  // Already-normalized data from a future public-settings adapter
  // (PublicSettingsModel.whatsappNumber) — this component never fetches
  // settings itself. `null` means "no WhatsApp number configured,"
  // never guessed or defaulted.
  whatsappNumber: string | null;
}

// #FVS022-FLOATING-WHATSAPP-BUTTON
//
// Purely presentational. Reuses buildWhatsAppHref directly (owned by
// FVS-014's #ARCHITECTURE-WHATSAPP-ADAPTER) rather than duplicating
// wa.me construction/encoding logic. Renders nothing if no valid
// destination exists — never a hardcoded fallback number
// (FRONTEND-VERTICAL-SLICE-PLAN.md FVS-022's own "never hardcode a
// fallback phone number" line).
//
// `--mobile-sticky-action-offset` is a CSS custom-property seam (not
// yet set by anything) so a future FVS-014 mobile sticky action bar
// can coordinate vertical position without this component inventing a
// magic pixel offset tied to a bar that doesn't exist yet.
export function FloatingWhatsAppButton({ whatsappNumber }: FloatingWhatsAppButtonProps) {
  if (!whatsappNumber) {
    return null;
  }

  const href = buildWhatsAppHref(whatsappNumber);
  if (!href) {
    return null;
  }

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Chat with us on WhatsApp"
      // Stitch §7 FAB: 56px circle, shadow-xl, scale on hover. Fill is
      // WhatsApp's own Teal Green (#128c7e, Dark Teal on hover) instead of
      // the #25d366 brand green: a white glyph on #25d366 is 2.0:1, below
      // the 3:1 non-text minimum; on Teal Green it is 4.1:1. z-30 keeps it
      // under the sticky header (40) and every dialog/sheet (50). The
      // offset respects the device safe area and the sticky-action seam.
      className="fixed z-30 flex h-14 w-14 [--fab-inset:1rem] tablet:[--fab-inset:2rem] items-center justify-center rounded-full bg-whatsapp-strong text-white shadow-xl ring-1 ring-white/40 transition-[transform,background-color] duration-200 ease-standard hover:scale-110 hover:bg-whatsapp-deep motion-reduce:transition-none motion-reduce:hover:scale-100"
      style={{
        right: "calc(var(--fab-inset) + env(safe-area-inset-right, 0px))",
        bottom: "calc(var(--fab-inset) + env(safe-area-inset-bottom, 0px) + var(--mobile-sticky-action-offset, 0px))",
      }}
    >
      <WhatsAppGlyph className="h-7 w-7" />
    </a>
  );
}
