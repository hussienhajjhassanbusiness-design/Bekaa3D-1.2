import { buildWhatsAppHref, buildWhatsAppProductMessage } from "@/lib/catalog/whatsapp";

export interface WhatsAppChatButtonProps {
  // Already-normalized digits-only destination, or null/absent when the
  // public setting is missing/disabled — the normalization step itself
  // belongs to a future settings adapter, never this component
  // (FVS-014-IMPLEMENTATION-PLAN.md §1).
  normalizedNumber: string | null;
  productName: string;
  label?: string;
}

// #FVS014-WHATSAPP-CHAT
//
// No order/API write happens on click — this is a plain anchor to a
// wa.me URL with a prefilled message, nothing more. Fails safely
// (renders nothing) when the destination is absent or fails the pure
// helper's digits-only precondition, rather than guessing a cleanup.
export function WhatsAppChatButton({ normalizedNumber, productName, label = "Chat on WhatsApp" }: WhatsAppChatButtonProps) {
  if (!normalizedNumber) {
    return null;
  }

  const href = buildWhatsAppHref(normalizedNumber, buildWhatsAppProductMessage(productName));
  if (!href) {
    return null;
  }

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-block rounded-md bg-brand-green px-4 py-2 text-text-on-brand"
    >
      {label}
    </a>
  );
}
