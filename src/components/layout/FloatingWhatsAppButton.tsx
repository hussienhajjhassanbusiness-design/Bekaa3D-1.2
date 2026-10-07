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
      className="fixed right-4 z-50 rounded-full bg-success p-3 text-white shadow-lg"
      style={{ bottom: "calc(1rem + var(--mobile-sticky-action-offset, 0px))" }}
    >
      <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" className="h-6 w-6" fill="currentColor">
        <path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5.1-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.1l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1-.2.2-.6.8-.8 1-.1.2-.3.2-.5.1-1.3-.6-2.2-1.1-3-2.5-.2-.3 0-.5.1-.6l.5-.6c.1-.2.1-.3 0-.5-.1-.2-.5-1.3-.7-1.7-.2-.4-.4-.3-.6-.3h-.5c-.2 0-.5.1-.7.3-.2.3-.9 1-.9 2.3s1 2.6 1.1 2.8c.1.1 1.8 2.8 4.4 3.8 2.1.8 2.1.5 2.5.5.4 0 1.3-.5 1.5-1 .2-.5.2-.9.1-1 0-.1-.2-.2-.4-.2Z" />
      </svg>
    </a>
  );
}
