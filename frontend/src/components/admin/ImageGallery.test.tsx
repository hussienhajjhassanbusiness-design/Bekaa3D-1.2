import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ImageGallery } from "./ImageGallery";
import type { GalleryImageModel } from "./ImageGallery";

// FVS-012-IMPLEMENTATION-PLAN.md T04 — frontend-normalized gallery
// presentation. No backend field names are claimed (GalleryImageModel is
// a UI shape only). Reorder is explicit Move Up/Down buttons, not
// pointer drag — the plan's own recorded decision (§5/T04): drag adds
// complexity without changing what's safe to ship now, and the
// architecture (onReorder(nextIds)) supports adding drag later without
// a redesign. Delete reuses the existing ConfirmDialog (FVS-007/009) —
// no new modal.

function makeImages(overrides: Partial<GalleryImageModel>[] = []): GalleryImageModel[] {
  const base: GalleryImageModel[] = [
    { id: "img-1", src: "/a.png", accessibleLabel: "Front view", isCover: true },
    { id: "img-2", src: "/b.png", accessibleLabel: "Side view", isCover: false },
    { id: "img-3", src: "/c.png", accessibleLabel: "Back view", isCover: false },
  ];
  return base.map((img, i) => ({ ...img, ...overrides[i] }));
}

describe("ImageGallery", () => {
  it("renders each image with its accessible label", () => {
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByRole("img", { name: "Front view" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Side view" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Back view" })).toBeInTheDocument();
  });

  it("shows the cover state as visible text, not icon/color alone", () => {
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText("Cover")).toBeInTheDocument();
  });

  it("calls onSetCover with the image id when Set as cover is activated", async () => {
    const onSetCover = vi.fn();
    const user = userEvent.setup();
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={onSetCover} onDelete={vi.fn()} />);

    const secondItem = screen.getByRole("img", { name: "Side view" }).closest("li")!;
    await user.click(within(secondItem).getByRole("button", { name: /set as cover/i }));

    expect(onSetCover).toHaveBeenCalledWith("img-2");
  });

  it("moving the second image up calls onReorder with the resulting id order", async () => {
    const onReorder = vi.fn();
    const user = userEvent.setup();
    render(<ImageGallery images={makeImages()} onReorder={onReorder} onSetCover={vi.fn()} onDelete={vi.fn()} />);

    const secondItem = screen.getByRole("img", { name: "Side view" }).closest("li")!;
    await user.click(within(secondItem).getByRole("button", { name: /move up/i }));

    expect(onReorder).toHaveBeenCalledWith(["img-2", "img-1", "img-3"]);
  });

  it("moving the second image down calls onReorder with the resulting id order", async () => {
    const onReorder = vi.fn();
    const user = userEvent.setup();
    render(<ImageGallery images={makeImages()} onReorder={onReorder} onSetCover={vi.fn()} onDelete={vi.fn()} />);

    const secondItem = screen.getByRole("img", { name: "Side view" }).closest("li")!;
    await user.click(within(secondItem).getByRole("button", { name: /move down/i }));

    expect(onReorder).toHaveBeenCalledWith(["img-1", "img-3", "img-2"]);
  });

  it("disables Move up for the first image", () => {
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={vi.fn()} />);
    const firstItem = screen.getByRole("img", { name: "Front view" }).closest("li")!;
    expect(within(firstItem).getByRole("button", { name: /move up/i })).toBeDisabled();
  });

  it("disables Move down for the last image", () => {
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={vi.fn()} />);
    const lastItem = screen.getByRole("img", { name: "Back view" }).closest("li")!;
    expect(within(lastItem).getByRole("button", { name: /move down/i })).toBeDisabled();
  });

  it("move buttons are real, keyboard-reachable native buttons", () => {
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={vi.fn()} />);
    const buttons = screen.getAllByRole("button", { name: /move (up|down)/i });
    for (const button of buttons) {
      expect(button.tagName).toBe("BUTTON");
    }
  });

  it("Delete opens the shared ConfirmDialog", async () => {
    const user = userEvent.setup();
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={vi.fn()} />);

    const firstItem = screen.getByRole("img", { name: "Front view" }).closest("li")!;
    await user.click(within(firstItem).getByRole("button", { name: /delete/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("Cancel in the delete dialog closes it without calling onDelete", async () => {
    const onDelete = vi.fn();
    const user = userEvent.setup();
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={onDelete} />);

    const firstItem = screen.getByRole("img", { name: "Front view" }).closest("li")!;
    await user.click(within(firstItem).getByRole("button", { name: /delete/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Confirm in the delete dialog calls onDelete with the image id", async () => {
    const onDelete = vi.fn();
    const user = userEvent.setup();
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={onDelete} />);

    const firstItem = screen.getByRole("img", { name: "Front view" }).closest("li")!;
    await user.click(within(firstItem).getByRole("button", { name: /delete/i }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    expect(onDelete).toHaveBeenCalledWith("img-1");
  });

  // Phase 5A final defect regression — the dialog must close and drop its
  // target once onDelete reports success, so a second confirm can never
  // re-target the already-deleted image.
  it("closes the dialog and clears the target after onDelete resolves true", async () => {
    const onDelete = vi.fn().mockResolvedValue(true);
    const user = userEvent.setup();
    const { rerender } = render(
      <ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={onDelete} />
    );

    const firstItem = screen.getByRole("img", { name: "Front view" }).closest("li")!;
    await user.click(within(firstItem).getByRole("button", { name: /delete/i }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: /^delete$/i }));

    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledWith("img-1");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // Refetch drops the deleted image; opening the dialog for another
    // image targets that image, never the stale one.
    rerender(
      <ImageGallery images={makeImages().slice(1)} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={onDelete} />
    );
    const sideItem = screen.getByRole("img", { name: "Side view" }).closest("li")!;
    await user.click(within(sideItem).getByRole("button", { name: /delete/i }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: /^delete$/i }));
    expect(onDelete).toHaveBeenCalledTimes(2);
    expect(onDelete).toHaveBeenLastCalledWith("img-2");
  });

  it("closes a dialog whose target image is no longer in the gallery", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={vi.fn()} />
    );
    const firstItem = screen.getByRole("img", { name: "Front view" }).closest("li")!;
    await user.click(within(firstItem).getByRole("button", { name: /delete/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    rerender(
      <ImageGallery images={makeImages().slice(1)} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={vi.fn()} />
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps the dialog open with the same target when onDelete resolves false", async () => {
    const onDelete = vi.fn().mockResolvedValue(false);
    const user = userEvent.setup();
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={onDelete} />);

    const firstItem = screen.getByRole("img", { name: "Front view" }).closest("li")!;
    await user.click(within(firstItem).getByRole("button", { name: /delete/i }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: /^delete$/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: /^delete$/i }));
    expect(onDelete).toHaveBeenCalledTimes(2);
    expect(onDelete).toHaveBeenLastCalledWith("img-1");
  });

  it("does not render an alt-text editor when onUpdateAltText is not provided", () => {
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.queryByLabelText(/alt text/i)).not.toBeInTheDocument();
  });

  it("renders an alt-text editor pre-filled with the image's current alt text, and saves the edited value", async () => {
    const onUpdateAltText = vi.fn();
    const user = userEvent.setup();
    render(
      <ImageGallery
        images={makeImages([{ altText: "Front" }])}
        onReorder={vi.fn()}
        onSetCover={vi.fn()}
        onDelete={vi.fn()}
        onUpdateAltText={onUpdateAltText}
      />
    );

    const firstItem = screen.getByRole("img", { name: "Front view" }).closest("li")!;
    const altTextInput = within(firstItem).getByLabelText("Alt text (image 1)");
    expect(altTextInput).toHaveValue("Front");

    await user.clear(altTextInput);
    await user.type(altTextInput, "Front view, angled");
    await user.click(within(firstItem).getByRole("button", { name: /save alt text/i }));

    expect(onUpdateAltText).toHaveBeenCalledWith("img-1", "Front view, angled");
  });

  it("gives each image a distinguishing alt-text label, never the same label repeated across rows", () => {
    render(
      <ImageGallery
        images={makeImages()}
        onReorder={vi.fn()}
        onSetCover={vi.fn()}
        onDelete={vi.fn()}
        onUpdateAltText={vi.fn()}
      />
    );
    expect(screen.getByLabelText("Alt text (image 1)")).toBeInTheDocument();
    expect(screen.getByLabelText("Alt text (image 2)")).toBeInTheDocument();
    expect(screen.getByLabelText("Alt text (image 3)")).toBeInTheDocument();
  });

  it("disables the alt-text save button while isUpdatingAltText", () => {
    render(
      <ImageGallery
        images={makeImages()}
        onReorder={vi.fn()}
        onSetCover={vi.fn()}
        onDelete={vi.fn()}
        onUpdateAltText={vi.fn()}
        isUpdatingAltText
      />
    );
    const firstItem = screen.getByRole("img", { name: "Front view" }).closest("li")!;
    expect(within(firstItem).getByRole("button", { name: /save alt text/i })).toBeDisabled();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<ImageGallery images={makeImages()} onReorder={vi.fn()} onSetCover={vi.fn()} onDelete={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
  });
});
