import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DialogShell } from "./DialogShell";

// Extracted from FVS-007's own ConfirmDialog so neither it nor any
// future dialog elsewhere in the app needs a second independent
// focus-trap/Escape/backdrop implementation (#SHARED-DIALOG-SHELL).
// Carries NO business/domain knowledge — title/
// description/actions are entirely the caller's `children`; this shell
// only owns the accessible-dialog mechanics (role, aria-modal, focus
// trap, Escape, backdrop click, focus restoration).

function renderShell(overrides: Partial<Parameters<typeof DialogShell>[0]> = {}) {
  const onClose = vi.fn();
  render(
    <div>
      <button type="button">trigger</button>
      <DialogShell open={true} onClose={onClose} labelledBy="t-id" describedBy="d-id" {...overrides}>
        <h2 id="t-id">Title</h2>
        <p id="d-id">Description</p>
        <button type="button">Cancel</button>
        <button type="button">Confirm</button>
      </DialogShell>
    </div>
  );
  return { onClose };
}

describe("DialogShell", () => {
  it("is absent from the DOM when closed", () => {
    render(
      <DialogShell open={false} onClose={vi.fn()} labelledBy="t-id">
        <h2 id="t-id">Title</h2>
      </DialogShell>
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is visible when open, with role=dialog and aria-modal", () => {
    renderShell();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("wires aria-labelledby/aria-describedby through to the dialog element", () => {
    renderShell();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-labelledby", "t-id");
    expect(dialog).toHaveAttribute("aria-describedby", "d-id");
  });

  it("renders exactly the supplied children, with no business/domain knowledge of its own", () => {
    renderShell();
    expect(screen.getByText("Title")).toBeInTheDocument();
    expect(screen.getByText("Description")).toBeInTheDocument();
  });

  it("calls onClose on Escape", async () => {
    const user = userEvent.setup();
    const { onClose } = renderShell();

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("suppresses Escape while isBusy is true", async () => {
    const user = userEvent.setup();
    const { onClose } = renderShell({ isBusy: true });

    await user.keyboard("{Escape}");

    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose on a backdrop click", async () => {
    const user = userEvent.setup();
    const { onClose } = renderShell();

    await user.click(screen.getByRole("dialog").parentElement!);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("suppresses a backdrop click while isBusy is true", async () => {
    const user = userEvent.setup();
    const { onClose } = renderShell({ isBusy: true });

    await user.click(screen.getByRole("dialog").parentElement!);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("does not close when clicking inside the dialog content", async () => {
    const user = userEvent.setup();
    const { onClose } = renderShell();

    await user.click(screen.getByText("Title"));

    expect(onClose).not.toHaveBeenCalled();
  });

  it("traps keyboard focus within the dialog (Tab from the last control wraps to the first)", async () => {
    const user = userEvent.setup();
    renderShell();

    const cancelButton = screen.getByRole("button", { name: "Cancel" });
    const confirmButton = screen.getByRole("button", { name: "Confirm" });

    confirmButton.focus();
    expect(confirmButton).toHaveFocus();
    await user.tab();

    expect(cancelButton).toHaveFocus();
  });

  it("restores focus to the triggering element when closed", () => {
    const onClose = vi.fn();
    const trigger = document.createElement("button");
    trigger.textContent = "trigger";
    document.body.appendChild(trigger);
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const { rerender } = render(
      <DialogShell open={true} onClose={onClose} labelledBy="t-id">
        <h2 id="t-id">Title</h2>
      </DialogShell>
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    rerender(
      <DialogShell open={false} onClose={onClose} labelledBy="t-id">
        <h2 id="t-id">Title</h2>
      </DialogShell>
    );

    expect(document.activeElement).toBe(trigger);
    document.body.removeChild(trigger);
  });

  it("stays within the viewport width at narrow sizes (mobile-safe structure)", () => {
    renderShell();
    const dialog = screen.getByRole("dialog");
    expect(dialog.className).toMatch(/max-w-/);
    expect(dialog.className).toMatch(/w-full/);
  });

  it("uses the exact existing default panel classes when panelClassName is omitted", () => {
    renderShell();
    const dialog = screen.getByRole("dialog");
    expect(dialog.className).toBe(
      "w-full max-w-md max-h-[90vh] overflow-y-auto rounded-lg bg-white p-6 shadow-elevation-3"
    );
  });

  it("replaces the panel classes entirely with a caller-supplied panelClassName (FVS-025 MiniCartDrawer seam)", () => {
    renderShell({ panelClassName: "fixed inset-y-0 right-0 h-full w-80 bg-white" });
    const dialog = screen.getByRole("dialog");
    expect(dialog.className).toBe("fixed inset-y-0 right-0 h-full w-80 bg-white");
  });
});
