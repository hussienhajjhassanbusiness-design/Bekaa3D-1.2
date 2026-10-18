import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RefundCreateForm } from "./RefundCreateForm";
import type { RefundLineCandidate } from "@/lib/admin/refundCreateModel";

// FVS-032-IMPLEMENTATION-PLAN.md T02/T03/T04 — per-line MoneyInput
// reuse against a server-supplied ceiling
// (#SECURITY-SERVER-REFUND-BALANCE-AUTHORITY). A digital candidate
// shows a plain, non-blocking warning once a nonzero amount is
// entered — there is no entitlement to revoke (ADR-019), so this is
// informational only and never gates submission. No shipping row
// exists anywhere: ADR-024 means nothing was ever charged for
// shipping.

const PHYSICAL: RefundLineCandidate = {
  lineId: "line-1",
  productDisplayName: "Garden Gnome",
  refundableBalanceCents: 1999,
  currency: "USD",
};

const DIGITAL: RefundLineCandidate = {
  lineId: "line-2",
  productDisplayName: "Dragon STL",
  refundableBalanceCents: 500,
  currency: "USD",
  isDigital: true,
};

describe("RefundCreateForm", () => {
  it("renders a labeled MoneyInput per line candidate, with the product name in the label", () => {
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[PHYSICAL]} onSubmit={vi.fn()} />);
    expect(screen.getByLabelText(/Garden Gnome/)).toBeInTheDocument();
  });

  it("displays the exact server-supplied refundable ceiling per line", () => {
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[PHYSICAL]} onSubmit={vi.fn()} />);
    expect(screen.getByText("$19.99")).toBeInTheDocument();
  });

  it("accepts an amount at or below the ceiling with no inline error", async () => {
    const user = userEvent.setup();
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[PHYSICAL]} onSubmit={vi.fn()} />);

    await user.type(screen.getByLabelText(/Garden Gnome/), "19.99");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("blocks an amount above the ceiling with an inline error — a UX precheck only", async () => {
    const user = userEvent.setup();
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[PHYSICAL]} onSubmit={vi.fn()} />);

    await user.type(screen.getByLabelText(/Garden Gnome/), "25.00");
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit refund" })).toBeDisabled();
  });

  it("stores integer cents with no floating-point drift", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[PHYSICAL]} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/Garden Gnome/), "0.10");
    await user.click(screen.getByRole("button", { name: "Submit refund" }));

    expect(onSubmit).toHaveBeenCalledWith({ lineAmountsCents: { "line-1": 10 } });
  });

  it("renders no shipping input — ADR-024 means nothing was ever charged for shipping", () => {
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[PHYSICAL, DIGITAL]} onSubmit={vi.fn()} />);
    expect(screen.queryByLabelText(/shipping/i)).not.toBeInTheDocument();
  });

  it("each line's selection is independent — entering an amount on one line never affects another", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[PHYSICAL, DIGITAL]} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/Garden Gnome/), "10.00");
    await user.click(screen.getByRole("button", { name: "Submit refund" }));

    expect(onSubmit).toHaveBeenCalledWith({
      lineAmountsCents: { "line-1": 1000, "line-2": null },
    });
  });

  it("disables the submit button while isSubmitting is true", () => {
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[PHYSICAL]} isSubmitting onSubmit={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Submit refund" })).toBeDisabled();
  });

  it("disables submit when nothing is selected", () => {
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[PHYSICAL]} onSubmit={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Submit refund" })).toBeDisabled();
  });

  it("a physical-only refund never shows the digital warning", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[PHYSICAL]} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/Garden Gnome/), "10.00");
    await user.click(screen.getByRole("button", { name: "Submit refund" }));

    expect(screen.queryByText(/cannot be un-sent/i)).not.toBeInTheDocument();
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("entering a nonzero amount on a digital line shows a plain warning, with no confirmation dialog", async () => {
    const user = userEvent.setup();
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[DIGITAL]} onSubmit={vi.fn()} />);

    await user.type(screen.getByLabelText(/Dragon STL/), "5.00");

    expect(screen.getByText(/cannot be un-sent/i)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("submits a digital refund immediately on click — the warning never gates submission", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[DIGITAL]} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/Dragon STL/), "5.00");
    await user.click(screen.getByRole("button", { name: "Submit refund" }));

    expect(onSubmit).toHaveBeenCalledWith({ lineAmountsCents: { "line-2": 500 } });
  });

  it("renders a server-supplied lineError verbatim, e.g. after an over-refund race rejection", () => {
    render(
      <RefundCreateForm
        orderDisplayId="order-1"
        lineCandidates={[PHYSICAL]}
        lineErrors={{ "line-1": "Another admin already refunded this line. Refresh and try again." }}
        onSubmit={vi.fn()}
      />
    );
    expect(screen.getByText("Another admin already refunded this line. Refresh and try again.")).toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<RefundCreateForm orderDisplayId="order-1" lineCandidates={[PHYSICAL]} onSubmit={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
