import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminCancelDialog } from "./AdminCancelDialog";

// FVS-031-IMPLEMENTATION-PLAN.md T04 — mirrors ManualConfirmDialog's
// (FVS-028) DialogShell + reason-textarea + whitespace-validation
// pattern exactly, since ConfirmDialog cannot cleanly host reason
// entry. The reason is local component state only — never persisted,
// logged, or placed in a URL. refundObligationMessage is rendered
// verbatim when supplied, never computed here
// (#ARCHITECTURE-REFUND-OBLIGATION-SERVER-OWNED).

describe("AdminCancelDialog", () => {
  it("renders an explicit admin-only title", () => {
    render(<AdminCancelDialog open lineId="line-1" onClose={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.getByText("Cancel order line")).toBeInTheDocument();
  });

  it("Confirm stays disabled until a non-empty reason is entered", async () => {
    const user = userEvent.setup();
    render(<AdminCancelDialog open lineId="line-1" onClose={vi.fn()} onConfirm={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();

    await user.type(screen.getByLabelText("Reason"), "Customer requested cancellation");
    expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
  });

  it("Confirm stays disabled for a whitespace-only reason", async () => {
    const user = userEvent.setup();
    render(<AdminCancelDialog open lineId="line-1" onClose={vi.fn()} onConfirm={vi.fn()} />);

    await user.type(screen.getByLabelText("Reason"), "   ");
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
  });

  it("confirming calls onConfirm with the lineId and the trimmed reason", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<AdminCancelDialog open lineId="line-9" onClose={vi.fn()} onConfirm={onConfirm} />);

    await user.type(screen.getByLabelText("Reason"), "  Customer requested cancellation  ");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(onConfirm).toHaveBeenCalledWith("line-9", "Customer requested cancellation");
  });

  it("renders the caller-supplied refundObligationMessage verbatim when present", () => {
    render(
      <AdminCancelDialog
        open
        lineId="line-1"
        refundObligationMessage="Cancelling after production may require a refund."
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />
    );
    expect(screen.getByText("Cancelling after production may require a refund.")).toBeInTheDocument();
  });

  it("renders no refund-obligation text when absent — never computes one locally", () => {
    render(<AdminCancelDialog open lineId="line-1" onClose={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.queryByText(/refund/i)).not.toBeInTheDocument();
  });

  it("disables Confirm and Cancel while isCancelling is true", async () => {
    const user = userEvent.setup();
    render(
      <AdminCancelDialog open lineId="line-1" isCancelling onClose={vi.fn()} onConfirm={vi.fn()} />
    );
    await user.type(screen.getByLabelText("Reason"), "reason");
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });

  it("does not render when open is false", () => {
    render(<AdminCancelDialog open={false} lineId="line-1" onClose={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<AdminCancelDialog open lineId="line-1" onClose={vi.fn()} onConfirm={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
