// Display-only date formatting for order pages (the server's ISO instants,
// shown in the viewer's own time zone). Never parses or computes dates.
export function formatOrderDate(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "long" }).format(new Date(iso));
}

export function formatOrderDateTime(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "long", timeStyle: "short" }).format(new Date(iso));
}

// Frontend-owned wording for the server's enums (the values themselves are
// never shown). Unknown values fall back to neutral text.
export function fulfillmentLabel(method: string | null): string {
  if (method === "delivery") return "Delivery";
  if (method === "pickup") return "Pickup";
  if (method === null) return "STL files only";
  return "Fulfillment unavailable";
}

export function paymentMethodLabel(method: string): string {
  if (method === "cash") return "Cash";
  if (method === "online") return "Online payment";
  return "Payment method unavailable";
}
