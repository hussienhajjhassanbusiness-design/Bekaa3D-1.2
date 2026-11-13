// #SHARED-WHATSAPP-GLYPH (redesign Batch 3)
//
// The WhatsApp mark, drawn locally (no remote asset), filled with
// currentColor. Always decorative: the link around it carries the name.
// Shared by the floating action and the product page's chat button.
export function WhatsAppGlyph({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" className={`shrink-0 ${className}`} fill="currentColor">
      <path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5.1-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.1l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1-.2.2-.6.8-.8 1-.1.2-.3.2-.5.1-1.3-.6-2.2-1.1-3-2.5-.2-.3 0-.5.1-.6l.5-.6c.1-.2.1-.3 0-.5-.1-.2-.5-1.3-.7-1.7-.2-.4-.4-.3-.6-.3h-.5c-.2 0-.5.1-.7.3-.2.3-.9 1-.9 2.3s1 2.6 1.1 2.8c.1.1 1.8 2.8 4.4 3.8 2.1.8 2.1.5 2.5.5.4 0 1.3-.5 1.5-1 .2-.5.2-.9.1-1 0-.1-.2-.2-.4-.2Z" />
    </svg>
  );
}
