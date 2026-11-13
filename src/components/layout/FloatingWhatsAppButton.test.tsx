import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { FloatingWhatsAppButton } from "./FloatingWhatsAppButton";
import { buildWhatsAppHref } from "@/lib/catalog/whatsapp";

// FVS-022-IMPLEMENTATION-PLAN.md T02 — purely presentational. This
// component never fetches public settings itself (that is a future
// adapter's job once GET /api/v1/settings/public's response envelope
// is confirmed — plan §0/§1); it only ever renders from an
// already-normalized `whatsappNumber` prop, and reuses
// `buildWhatsAppHref` directly rather than duplicating wa.me
// construction/encoding logic (#ARCHITECTURE-WHATSAPP-ADAPTER, owned
// by FVS-014).

describe("FloatingWhatsAppButton", () => {
  it("renders nothing when no WhatsApp number is configured (null)", () => {
    const { container } = render(<FloatingWhatsAppButton whatsappNumber={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the supplied number fails buildWhatsAppHref's digits-only precondition", () => {
    const { container } = render(<FloatingWhatsAppButton whatsappNumber="+961 70 123456" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a real anchor when a valid WhatsApp number is supplied", () => {
    render(<FloatingWhatsAppButton whatsappNumber="96170123456" />);
    expect(screen.getByRole("link")).toBeInTheDocument();
  });

  it("uses the exact required accessible name", () => {
    render(<FloatingWhatsAppButton whatsappNumber="96170123456" />);
    expect(screen.getByRole("link", { name: "Chat with us on WhatsApp" })).toBeInTheDocument();
  });

  it("builds its href via the exact same buildWhatsAppHref call a caller would make — no duplicated WhatsApp URL logic", () => {
    render(<FloatingWhatsAppButton whatsappNumber="96170123456" />);
    const link = screen.getByRole("link", { name: "Chat with us on WhatsApp" });
    expect(link).toHaveAttribute("href", buildWhatsAppHref("96170123456")!);
  });

  it("opens WhatsApp in a new tab with safe rel attributes", () => {
    render(<FloatingWhatsAppButton whatsappNumber="96170123456" />);
    const link = screen.getByRole("link", { name: "Chat with us on WhatsApp" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(link).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
  });

  it("never hardcodes a fallback phone number when none is configured", () => {
    render(<FloatingWhatsAppButton whatsappNumber={null} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<FloatingWhatsAppButton whatsappNumber="96170123456" />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<FloatingWhatsAppButton whatsappNumber="96170123456" />);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it("renders fixed/floating positioning classes", () => {
    render(<FloatingWhatsAppButton whatsappNumber="96170123456" />);
    const link = screen.getByRole("link", { name: "Chat with us on WhatsApp" });
    expect(link.className).toMatch(/fixed/);
  });

  it("does not itself own a public-settings fetch — it only consumes an already-resolved prop", () => {
    // Structural proof: the component's only data input is the
    // whatsappNumber prop. Rendering with a valid number and again with
    // null produces the two documented outcomes deterministically, with
    // no internal async/loading state ever observable.
    const { rerender, container } = render(<FloatingWhatsAppButton whatsappNumber={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<FloatingWhatsAppButton whatsappNumber="96170123456" />);
    expect(screen.getByRole("link")).toBeInTheDocument();
  });

  it("Batch 3: a 56px circle on WhatsApp's Teal Green (white glyph 4.1:1), never the failing #25d366 fill", () => {
    render(<FloatingWhatsAppButton whatsappNumber="96170123456" />);
    const link = screen.getByRole("link", { name: "Chat with us on WhatsApp" });
    expect(link).toHaveClass("h-14", "w-14", "bg-whatsapp-strong", "text-white");
    expect(link).not.toHaveClass("bg-whatsapp");
  });

  it("Batch 3: stays under the sticky header (z-40) and every dialog or sheet (z-50)", () => {
    render(<FloatingWhatsAppButton whatsappNumber="96170123456" />);
    expect(screen.getByRole("link")).toHaveClass("z-30");
  });

  it("Batch 3: keeps clear of the device safe area and the sticky-action seam", () => {
    render(<FloatingWhatsAppButton whatsappNumber="96170123456" />);
    const style = screen.getByRole("link").getAttribute("style") ?? "";
    expect(style).toContain("safe-area-inset-bottom");
    expect(style).toContain("--mobile-sticky-action-offset");
  });

  it("Batch 3: its hover scale is switched off under reduced motion", () => {
    render(<FloatingWhatsAppButton whatsappNumber="96170123456" />);
    expect(screen.getByRole("link")).toHaveClass("motion-reduce:hover:scale-100");
  });
});
