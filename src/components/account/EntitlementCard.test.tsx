import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { EntitlementCard } from "./EntitlementCard";
import type { EntitlementModel } from "@/lib/entitlements/entitlementModel";

// FVS-020-IMPLEMENTATION-PLAN.md T02 — presentational only, no
// network. `actionSlot` is a generic seam FVS-021 populates with its
// own `DownloadButton` later — this component never guesses a
// download endpoint or builds a second temporary download control.

function makeEntitlement(overrides: Partial<EntitlementModel> = {}): EntitlementModel {
  return { id: "ent-1", productDisplayName: "Dragon STL", ...overrides };
}

describe("EntitlementCard", () => {
  it("renders the product display name", () => {
    render(<EntitlementCard entitlement={makeEntitlement()} />);
    expect(screen.getByText("Dragon STL")).toBeInTheDocument();
  });

  it("renders the current version label when supplied", () => {
    render(<EntitlementCard entitlement={makeEntitlement({ currentVersionLabel: "Version 3" })} />);
    expect(screen.getByText("Version 3")).toBeInTheDocument();
  });

  it("renders no stray version text when the label is absent", () => {
    render(<EntitlementCard entitlement={makeEntitlement()} />);
    expect(screen.queryByText(/undefined/i)).not.toBeInTheDocument();
  });

  it("renders a decorative thumbnail when supplied, without duplicating the product name as alt text", () => {
    render(<EntitlementCard entitlement={makeEntitlement({ thumbnailSrc: "/thumb.png" })} />);
    const img = document.querySelector("img");
    expect(img).toHaveAttribute("src", "/thumb.png");
    expect(img).toHaveAttribute("alt", "");
  });

  it("renders no image element when no thumbnail is supplied", () => {
    render(<EntitlementCard entitlement={makeEntitlement()} />);
    expect(document.querySelector("img")).toBeNull();
  });

  it("renders the supplied action slot content", () => {
    render(<EntitlementCard entitlement={makeEntitlement()} actionSlot={<a href="/x">Download Dragon STL</a>} />);
    expect(screen.getByRole("link", { name: "Download Dragon STL" })).toBeInTheDocument();
  });

  it("adds no interactive element of its own beyond the supplied action slot (no overlapping click targets)", () => {
    render(<EntitlementCard entitlement={makeEntitlement()} actionSlot={<a href="/x">Download</a>} />);
    const interactive = [...screen.queryAllByRole("link"), ...screen.queryAllByRole("button")];
    expect(interactive).toHaveLength(1);
  });

  it("renders no action slot at all when none is supplied", () => {
    render(<EntitlementCard entitlement={makeEntitlement()} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<EntitlementCard entitlement={makeEntitlement()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
