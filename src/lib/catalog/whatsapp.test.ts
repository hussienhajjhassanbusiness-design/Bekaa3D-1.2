import { describe, it, expect } from "vitest";
import { buildWhatsAppHref, buildWhatsAppProductMessage } from "./whatsapp";

// FVS-014-IMPLEMENTATION-PLAN.md T04 — pure helpers only. The public
// WhatsApp number setting's exact stored format is NOT confirmed
// (FVS-014-IMPLEMENTATION-PLAN.md §1) — this module does NOT normalize
// an arbitrary setting value (that would mean inventing a normalization
// rule); its precondition is explicit: `normalizedNumber` must already
// be digits only. A value that doesn't meet that precondition is
// rejected (returns null), never silently "cleaned up."

describe("buildWhatsAppHref", () => {
  it("builds a wa.me href with the exact normalized number", () => {
    const href = buildWhatsAppHref("96170123456", "Hello");
    expect(href).toBe("https://wa.me/96170123456?text=Hello");
  });

  it("URL-encodes the message safely", () => {
    const href = buildWhatsAppHref("96170123456", 'Hi, I\'m interested in "Widget & Co"');
    expect(href).not.toBeNull();
    const url = new URL(href!);
    expect(url.searchParams.get("text")).toBe('Hi, I\'m interested in "Widget & Co"');
  });

  it("never embeds raw unencoded special characters in the href string", () => {
    const href = buildWhatsAppHref("96170123456", "<script>alert(1)</script>");
    expect(href).not.toContain("<script>");
  });

  it("returns null for an empty number — fails safely rather than guessing", () => {
    expect(buildWhatsAppHref("", "Hello")).toBeNull();
  });

  it("returns null for a number containing a plus sign — precondition is digits only, never normalized here", () => {
    expect(buildWhatsAppHref("+96170123456", "Hello")).toBeNull();
  });

  it("returns null for a number containing spaces", () => {
    expect(buildWhatsAppHref("961 70 123456", "Hello")).toBeNull();
  });

  it("returns null for a number containing hyphens", () => {
    expect(buildWhatsAppHref("961-70-123456", "Hello")).toBeNull();
  });
});

describe("buildWhatsAppProductMessage", () => {
  it("includes the exact product name", () => {
    expect(buildWhatsAppProductMessage("Bekaa3D Mini Stand")).toContain("Bekaa3D Mini Stand");
  });
});
