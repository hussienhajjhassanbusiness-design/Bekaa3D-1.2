import { WhatsAppGlyph } from "@/components/ui/WhatsAppGlyph";
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
      // Stitch STL-detail "WHATSAPP" secondary action, made accessible: a
      // neutral outline button with dark text and the glyph in WhatsApp's
      // Teal Green (4.1:1 on white). Green text or a white-on-#25d366 fill
      // would fail contrast (COMPONENT-MIGRATION "WhatsAppChatButton").
      className="inline-flex min-h-13 w-full items-center justify-center gap-2 rounded-control border-2 border-whatsapp-strong/40 bg-surface-container-lowest px-6 py-3 font-label text-label-caps uppercase text-on-surface transition-colors duration-200 hover:border-whatsapp-strong hover:bg-whatsapp/10"
    >
      <WhatsAppGlyph className="h-5 w-5 text-whatsapp-strong" />
      {label}
    </a>
  );
}
