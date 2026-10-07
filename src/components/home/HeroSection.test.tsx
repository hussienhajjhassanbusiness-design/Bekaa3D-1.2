import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { HeroSection } from "./HeroSection";

// FVS-022-IMPLEMENTATION-PLAN.md T03 — brand-focused, reusable. The
// default heading is the one approved copy fragment anywhere in the
// repository (the brand tagline), chosen deliberately so that if this
// component is ever composed onto `/`, e2e/smoke.spec.ts's existing
// assertion ("Bekaa3D — Engineered Grade 3D Solutions" heading on `/`)
// keeps passing unmodified. CTAs are only rendered when explicitly
// supplied — never a disabled anchor, never a default/invented
// destination, since no currently-valid home-page CTA route exists yet
// (plan §0).

const TAGLINE = "Bekaa3D — Engineered Grade 3D Solutions";

describe("HeroSection", () => {
  it("renders the approved brand tagline as the heading when none is supplied", () => {
    render(<HeroSection />);
    expect(screen.getByRole("heading", { level: 1, name: TAGLINE })).toBeInTheDocument();
  });

  it("renders exactly one h1", () => {
    render(<HeroSection />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("renders a caller-supplied heading override instead of the default", () => {
    render(<HeroSection heading="Custom Heading" />);
    expect(screen.getByRole("heading", { level: 1, name: "Custom Heading" })).toBeInTheDocument();
    expect(screen.queryByText(TAGLINE)).not.toBeInTheDocument();
  });

  it("renders supporting copy when supplied", () => {
    render(<HeroSection supportingCopy="Custom 3D parts, made to order." />);
    expect(screen.getByText("Custom 3D parts, made to order.")).toBeInTheDocument();
  });

  it("renders no supporting copy element when none is supplied", () => {
    const { container } = render(<HeroSection />);
    expect(container.querySelectorAll("p")).toHaveLength(0);
  });

  it("renders a real anchor for a supplied primary CTA, using the exact label/href", () => {
    render(<HeroSection primaryCta={{ label: "Browse the Shop", href: "/shop" }} />);
    const link = screen.getByRole("link", { name: "Browse the Shop" });
    expect(link).toHaveAttribute("href", "/shop");
  });

  it("renders a real anchor for a supplied secondary CTA, using the exact label/href", () => {
    render(<HeroSection secondaryCta={{ label: "Bring Your Idea", href: "/bring-your-idea" }} />);
    const link = screen.getByRole("link", { name: "Bring Your Idea" });
    expect(link).toHaveAttribute("href", "/bring-your-idea");
  });

  it("renders no CTA link at all when none is supplied — never a disabled or default anchor", () => {
    render(<HeroSection />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders both CTAs together when both are supplied", () => {
    render(
      <HeroSection
        primaryCta={{ label: "Browse the Shop", href: "/shop" }}
        secondaryCta={{ label: "Contact Us", href: "/contact" }}
      />
    );
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });
});
