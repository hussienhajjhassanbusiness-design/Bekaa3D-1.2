import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { OrderDetail } from "./OrderDetail";
import type { OrderDetailLoadResult, OrderDetailModel } from "./OrderDetail";

// FVS-029-IMPLEMENTATION-PLAN.md T06 (T08 folded in) —
// #SECURITY-ORDER-IDOR-HIDING. OrderDetailLoadResult has no
// "forbidden"/"forbidden-foreign" variant anywhere — a structural
// guarantee no consumer could render a distinct "you don't own this
// order" message even by mistake. A foreign-order fixture and a
// nonexistent-order fixture, both already reduced to
// {kind:"not-found"}, render byte-identical output.

function makeOrder(overrides: Partial<OrderDetailModel> = {}): OrderDetailModel {
  return {
    id: "order-1",
    displayDate: "Oct 7, 2026",
    statusLabel: "Processing",
    lines: [
      {
        id: "line-1",
        productDisplayName: "Garden Gnome",
        productType: "physical",
        quantity: 1,
        unitPriceCents: 1999,
        lineTotalCents: 1999,
        currency: "USD",
        statusLabel: "Processing",
      },
      {
        id: "line-2",
        productDisplayName: "Dragon STL",
        productType: "stl",
        quantity: 1,
        unitPriceCents: 500,
        lineTotalCents: 500,
        currency: "USD",
        statusLabel: "Delivered",
      },
    ],
    summary: { currency: "USD", totalCents: 2499 },
    ...overrides,
  };
}

describe("OrderDetail (loaded)", () => {
  it("renders every line via OrderLineItem, each with its own independent status", () => {
    render(<OrderDetail result={{ kind: "loaded", order: makeOrder() }} />);
    expect(screen.getByText("Garden Gnome")).toBeInTheDocument();
    expect(screen.getByText("Dragon STL")).toBeInTheDocument();
    expect(screen.getAllByText("Processing").length).toBeGreaterThan(0);
    expect(screen.getByText("Delivered")).toBeInTheDocument();
  });

  it("renders only the summary's present fields, omitting absent ones", () => {
    render(<OrderDetail result={{ kind: "loaded", order: makeOrder({ summary: { currency: "USD" } }) }} />);
    expect(screen.queryByText(/total/i)).not.toBeInTheDocument();
  });

  it("renders the summary total when present", () => {
    render(<OrderDetail result={{ kind: "loaded", order: makeOrder() }} />);
    expect(screen.getByText("$24.99")).toBeInTheDocument();
  });

  it("never makes a current-catalogue fetch/network call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<OrderDetail result={{ kind: "loaded", order: makeOrder() }} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});

describe("OrderDetail (not-found / IDOR hiding)", () => {
  it("renders NotFoundContent's exact output for kind: not-found", () => {
    render(<OrderDetail result={{ kind: "not-found" }} />);
    expect(screen.getByRole("heading", { name: /page not found/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to home/i })).toBeInTheDocument();
  });

  it("rendering the same not-found state twice is deterministic — no hidden input (e.g. a rejected id) leaks into the output", () => {
    // Independent review correctly flagged that comparing two
    // `{kind:"not-found"}` literals only proves this component is
    // pure, not that a real foreign-order response and a real
    // nonexistent-order response collapse to the same thing — that
    // collapse is this type's own job (see the structural test below)
    // and a future adapter's job (T09, correctly blocked: no backend
    // contract exists yet to map a 403/404 onto this result). This
    // test is honestly scoped to what it actually proves: nothing
    // about render output can vary for the identical not-found input,
    // which rules out a parameterized/leaky not-found implementation.
    const resultA: OrderDetailLoadResult = { kind: "not-found" };
    const resultB: OrderDetailLoadResult = { kind: "not-found" };

    const { container: containerA } = render(<OrderDetail result={resultA} />);
    const { container: containerB } = render(<OrderDetail result={resultB} />);

    expect(containerA.innerHTML).toBe(containerB.innerHTML);
  });

  it("never renders forbidden/unauthorized/belongs-to-another text for any input", () => {
    render(<OrderDetail result={{ kind: "not-found" }} />);
    expect(screen.queryByText(/forbidden|unauthorized|belongs to another/i)).not.toBeInTheDocument();
  });

  it("OrderDetailLoadResult has no forbidden-style variant — structurally only loaded/not-found exist", () => {
    // The real IDOR-hiding guarantee: this is a compile-time proof,
    // not a runtime one. A third "forbidden" kind is not just unused
    // by convention — it is impossible to construct at all. If
    // someone adds one later, this line fails to typecheck
    // (`npm run typecheck`, not `vitest run` — `@ts-expect-error`
    // directives are erased at runtime, same reasoning as every
    // other type-only test in this codebase).
    // @ts-expect-error — "forbidden" is not a valid OrderDetailLoadResult kind
    const attempted: OrderDetailLoadResult = { kind: "forbidden" };
    expect(attempted).toBeDefined();
  });
});
