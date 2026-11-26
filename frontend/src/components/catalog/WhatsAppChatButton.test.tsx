import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { WhatsAppChatButton } from "./WhatsAppChatButton";

// FVS-014-IMPLEMENTATION-PLAN.md T04 — presentational only. No order/
// API write happens on click — this is a plain anchor to a wa.me URL.
// Fails safely (renders nothing) when the destination is absent or
// doesn't meet the normalized-digits-only precondition
// (src/lib/catalog/whatsapp.ts).

describe("WhatsAppChatButton", () => {
  it("renders an accessible link when a valid normalized number is supplied", () => {
    render(<WhatsAppChatButton normalizedNumber="96170123456" productName="Widget" />);
    expect(screen.getByRole("link", { name: /whatsapp/i })).toBeInTheDocument();
  });

  it("builds the href with the exact normalized number", () => {
    render(<WhatsAppChatButton normalizedNumber="96170123456" productName="Widget" />);
    const href = screen.getByRole("link").getAttribute("href")!;
    expect(href.startsWith("https://wa.me/96170123456")).toBe(true);
  });

  it("includes the product name in the prefilled message", () => {
    render(<WhatsAppChatButton normalizedNumber="96170123456" productName="Bekaa3D Mini Stand" />);
    const href = screen.getByRole("link").getAttribute("href")!;
    const url = new URL(href);
    expect(url.searchParams.get("text")).toContain("Bekaa3D Mini Stand");
  });

  it("encodes special characters in the product name safely", () => {
    render(<WhatsAppChatButton normalizedNumber="96170123456" productName='<script>alert(1)</script>' />);
    const href = screen.getByRole("link").getAttribute("href")!;
    expect(href).not.toContain("<script>");
  });

  it("opens in a new tab with safe rel behavior", () => {
    render(<WhatsAppChatButton normalizedNumber="96170123456" productName="Widget" />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders nothing when the destination number is absent", () => {
    render(<WhatsAppChatButton normalizedNumber={null} productName="Widget" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders nothing when the destination number is invalid (not digits-only)", () => {
    render(<WhatsAppChatButton normalizedNumber="+961 70-123456" productName="Widget" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<WhatsAppChatButton normalizedNumber="96170123456" productName="Widget" />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("Batch 3: dark label text with a decorative glyph — the name is only the label", () => {
    render(<WhatsAppChatButton normalizedNumber="96170123456" productName="Widget" />);
    const link = screen.getByRole("link", { name: "Chat on WhatsApp" });
    expect(link).toHaveClass("text-on-surface");
    expect(link.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});
