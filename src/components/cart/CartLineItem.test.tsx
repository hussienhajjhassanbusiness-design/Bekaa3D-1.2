import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CartLineItem } from "./CartLineItem";
import type { CartLineModel } from "@/lib/cart/cartModel";

// FVS-025-IMPLEMENTATION-PLAN.md T03 — presentational only, no
// network. Required callback seams (onQuantityChange/onRemove) mirror
// AddressList.onDelete's precedent — wired to a real mutation only
// once T08 unblocks.

function makePhysicalLine(overrides: Partial<CartLineModel> = {}): CartLineModel {
  return {
    id: "line-1",
    productId: "prod-1",
    productDisplayName: "Garden Gnome",
    productType: "physical",
    quantity: 2,
    maxQuantity: 5,
    snapshotPriceCents: 1999,
    currency: "USD",
    ...overrides,
  };
}

function makeStlLine(overrides: Partial<CartLineModel> = {}): CartLineModel {
  return {
    id: "line-2",
    productId: "prod-2",
    productDisplayName: "Dragon STL",
    productType: "stl",
    quantity: 1,
    snapshotPriceCents: 500,
    currency: "USD",
    ...overrides,
  };
}

describe("CartLineItem (physical)", () => {
  it("renders the product name and a working quantity stepper with accessible names", async () => {
    const onQuantityChange = vi.fn();
    const user = userEvent.setup();
    render(<CartLineItem line={makePhysicalLine()} onQuantityChange={onQuantityChange} onRemove={vi.fn()} />);

    expect(screen.getByText("Garden Gnome")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /increase quantity of garden gnome/i }));
    expect(onQuantityChange).toHaveBeenCalledWith("line-1", 3);

    await user.click(screen.getByRole("button", { name: /decrease quantity of garden gnome/i }));
    expect(onQuantityChange).toHaveBeenCalledWith("line-1", 1);
  });

  it("announces the current quantity in a live region", () => {
    render(<CartLineItem line={makePhysicalLine({ quantity: 3 })} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("3");
  });

  it("disables the increment button once quantity reaches maxQuantity", () => {
    render(<CartLineItem line={makePhysicalLine({ quantity: 5, maxQuantity: 5 })} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByRole("button", { name: /increase quantity/i })).toBeDisabled();
  });

  it("does not disable the increment button when no maxQuantity is supplied", () => {
    render(<CartLineItem line={makePhysicalLine({ maxQuantity: undefined })} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByRole("button", { name: /increase quantity/i })).toBeEnabled();
  });

  it("disables the decrement button at quantity 1 — reaching 0 via the stepper is never valid; Remove is the explicit action for that", () => {
    render(<CartLineItem line={makePhysicalLine({ quantity: 1 })} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByRole("button", { name: /decrease quantity/i })).toBeDisabled();
  });

  it("does not call onQuantityChange with 0 even if the disabled decrement button were somehow activated", () => {
    const onQuantityChange = vi.fn();
    render(<CartLineItem line={makePhysicalLine({ quantity: 1 })} onQuantityChange={onQuantityChange} onRemove={vi.fn()} />);
    screen.getByRole("button", { name: /decrease quantity/i }).click();
    expect(onQuantityChange).not.toHaveBeenCalled();
  });
});

describe("CartLineItem (STL)", () => {
  it("renders a fixed quantity with no stepper controls at all", () => {
    render(<CartLineItem line={makeStlLine()} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByText(/qty.*1/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /increase quantity/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /decrease quantity/i })).not.toBeInTheDocument();
  });
});

describe("CartLineItem (price change)", () => {
  it("shows both the original and current price plus a note when they differ", () => {
    render(
      <CartLineItem
        line={makePhysicalLine({ snapshotPriceCents: 1000, currentPriceCents: 1200 })}
        onQuantityChange={vi.fn()}
        onRemove={vi.fn()}
      />
    );
    expect(screen.getByText("$10.00")).toBeInTheDocument();
    expect(screen.getByText("$12.00")).toBeInTheDocument();
    expect(screen.getByText(/price updated/i)).toBeInTheDocument();
  });

  it("shows no price-updated note when prices match", () => {
    render(
      <CartLineItem
        line={makePhysicalLine({ snapshotPriceCents: 1000, currentPriceCents: 1000 })}
        onQuantityChange={vi.fn()}
        onRemove={vi.fn()}
      />
    );
    expect(screen.queryByText(/price updated/i)).not.toBeInTheDocument();
  });

  it("shows no price-updated note when currentPriceCents is absent", () => {
    render(<CartLineItem line={makePhysicalLine({ currentPriceCents: undefined })} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.queryByText(/price updated/i)).not.toBeInTheDocument();
  });
});

describe("CartLineItem (unavailable notice)", () => {
  it("renders a caller-supplied unavailable notice as an alert", () => {
    render(
      <CartLineItem line={makePhysicalLine()} onQuantityChange={vi.fn()} onRemove={vi.fn()} unavailableNotice="This item is no longer available." />
    );
    expect(screen.getByRole("alert")).toHaveTextContent("This item is no longer available.");
  });

  it("renders no alert when no notice is supplied", () => {
    render(<CartLineItem line={makePhysicalLine()} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("CartLineItem (remove)", () => {
  it("always renders a Remove button that calls onRemove with the exact line id", async () => {
    const onRemove = vi.fn();
    const user = userEvent.setup();
    render(<CartLineItem line={makeStlLine()} onQuantityChange={vi.fn()} onRemove={onRemove} />);

    await user.click(screen.getByRole("button", { name: /remove/i }));

    expect(onRemove).toHaveBeenCalledWith("line-2");
  });
});

describe("CartLineItem (safety)", () => {
  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<CartLineItem line={makePhysicalLine()} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<CartLineItem line={makePhysicalLine()} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
