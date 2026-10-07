import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProductImageGallery } from "./ProductImageGallery";
import type { ProductGalleryImage } from "./ProductImageGallery";

// FVS-014-IMPLEMENTATION-PLAN.md T03 — PUBLIC viewer only. No admin
// actions (Move up/down, Set as cover, Delete) are ever rendered here —
// deliberately a separate component from FVS-012's admin ImageGallery,
// not a shared one forced to support two very different interaction
// models (see plan §5/T03 for the extraction decision). Ordered array
// input: the first image is the initial/main image (the future
// adapter's job to put the cover image first), so no separate `isCover`
// flag exists in this public-facing model.

const IMAGES: ProductGalleryImage[] = [
  { id: "img-1", src: "/front.png", alt: "Front view" },
  { id: "img-2", src: "/side.png", alt: "Side view" },
  { id: "img-3", src: "/back.png", alt: "Back view" },
];

describe("ProductImageGallery", () => {
  it("shows the first image as the main image by default", () => {
    render(<ProductImageGallery images={IMAGES} />);
    expect(screen.getByTestId("product-gallery-main-image")).toHaveAttribute("alt", "Front view");
  });

  it("renders one thumbnail button per image", () => {
    render(<ProductImageGallery images={IMAGES} />);
    expect(screen.getAllByRole("button")).toHaveLength(3);
  });

  it("switches the main image when a thumbnail is activated", async () => {
    const user = userEvent.setup();
    render(<ProductImageGallery images={IMAGES} />);

    await user.click(screen.getByRole("button", { name: /side view/i }));

    expect(screen.getByTestId("product-gallery-main-image")).toHaveAttribute("alt", "Side view");
  });

  it("marks only the active thumbnail with aria-current", async () => {
    const user = userEvent.setup();
    render(<ProductImageGallery images={IMAGES} />);

    await user.click(screen.getByRole("button", { name: /side view/i }));

    expect(screen.getByRole("button", { name: /side view/i })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: /front view/i })).not.toHaveAttribute("aria-current", "true");
  });

  it("thumbnails are real, keyboard-reachable buttons", () => {
    render(<ProductImageGallery images={IMAGES} />);
    for (const button of screen.getAllByRole("button")) {
      expect(button.tagName).toBe("BUTTON");
    }
  });

  it("each thumbnail carries meaningful accessible alt text, not a generic label", () => {
    render(<ProductImageGallery images={IMAGES} />);
    const sideThumbnail = screen.getByRole("button", { name: /side view/i });
    const backThumbnail = screen.getByRole("button", { name: /back view/i });
    expect(within(sideThumbnail).getByRole("img")).toHaveAttribute("alt", "Side view");
    expect(within(backThumbnail).getByRole("img")).toHaveAttribute("alt", "Back view");
  });

  it("renders no admin reorder/cover/delete controls", () => {
    render(<ProductImageGallery images={IMAGES} />);
    expect(screen.queryByText(/move up/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/move down/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/set as cover/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/delete/i)).not.toBeInTheDocument();
  });

  it("handles an empty image array without crashing", () => {
    render(<ProductImageGallery images={[]} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<ProductImageGallery images={IMAGES} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<ProductImageGallery images={IMAGES} />);
    expect(spy).not.toHaveBeenCalled();
  });
});
