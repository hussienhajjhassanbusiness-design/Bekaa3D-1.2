import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OrderList } from "./OrderList";
import type { OrderListFilters, OrderListItemModel } from "@/lib/orders/orderModel";

// FVS-029-IMPLEMENTATION-PLAN.md T05 — presentational only, no
// network. Desktop table / mobile cards via CSS-only dual render.
// Filters are presentational-only this batch: statusOptions is
// caller/config-driven, never a hardcoded list; forward-only cursor
// seam, no Previous control anywhere.

const ITEMS: readonly OrderListItemModel[] = [
  { id: "order-1", displayDate: "Oct 7, 2026", statusLabel: "Processing", totalCents: 5000, currency: "USD" },
  { id: "order-2", displayDate: "Oct 5, 2026", statusLabel: "Delivered", totalCents: 1200, currency: "USD" },
];

const EMPTY_FILTERS: OrderListFilters = { status: null, dateFrom: null, dateTo: null, cursor: null };
const STATUS_OPTIONS = [
  { value: "processing", label: "Processing" },
  { value: "delivered", label: "Delivered" },
];

function baseProps(overrides: Partial<Parameters<typeof OrderList>[0]> = {}) {
  return {
    items: ITEMS,
    filters: EMPTY_FILTERS,
    onFiltersChange: vi.fn(),
    ...overrides,
  };
}

describe("OrderList", () => {
  it("shows a loading state", () => {
    render(<OrderList {...baseProps({ items: [], isLoading: true })} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows a safe error message with a retry action", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<OrderList {...baseProps({ items: [], isError: true, errorMessage: "Couldn't load your orders.", onRetry })} />);

    expect(screen.getByText("Couldn't load your orders.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows a safe empty-history message — no fake rows", () => {
    render(<OrderList {...baseProps({ items: [] })} />);
    expect(screen.getByText(/no orders/i)).toBeInTheDocument();
  });

  it("renders every order in both the desktop table and mobile card markup", () => {
    render(<OrderList {...baseProps()} />);
    expect(screen.getAllByText("Oct 7, 2026").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Oct 5, 2026").length).toBeGreaterThan(0);
  });

  it("the desktop table is CSS-hidden on narrow widths, not via JS viewport detection", () => {
    render(<OrderList {...baseProps()} />);
    const table = screen.getByRole("table", { hidden: true });
    expect(table.className).toMatch(/hidden/);
    expect(table.className).toMatch(/tablet:table/);
  });

  it("renders a mobile stacked list that is CSS-hidden at tablet and above", () => {
    render(<OrderList {...baseProps()} />);
    const lists = screen.getAllByRole("list", { hidden: true });
    const mobileList = lists.find((list) => list.className.includes("tablet:hidden"));
    expect(mobileList).toBeTruthy();
  });

  it("renders only the supplied statusOptions, never a hardcoded list", () => {
    render(<OrderList {...baseProps({ statusOptions: STATUS_OPTIONS })} />);
    const select = screen.getByRole("combobox", { name: /status/i });
    expect(screen.getByRole("option", { name: "Processing" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Delivered" })).toBeInTheDocument();
    expect(select.querySelectorAll("option")).toHaveLength(STATUS_OPTIONS.length + 1); // +1 for "All"
  });

  it("renders no status filter at all when statusOptions is omitted", () => {
    render(<OrderList {...baseProps()} />);
    expect(screen.queryByRole("combobox", { name: /status/i })).not.toBeInTheDocument();
  });

  it("date inputs call onFiltersChange with the typed value", async () => {
    const onFiltersChange = vi.fn();
    const user = userEvent.setup();
    render(<OrderList {...baseProps({ onFiltersChange })} />);

    await user.type(screen.getByLabelText(/from/i), "2026-01-01");

    expect(onFiltersChange).toHaveBeenCalledWith(expect.objectContaining({ dateFrom: "2026-01-01" }));
  });

  it("onNext fires only when hasNext is true, and no Previous control exists anywhere", async () => {
    const onNext = vi.fn();
    const user = userEvent.setup();
    render(<OrderList {...baseProps({ hasNext: true, onNext })} />);

    expect(screen.queryByRole("button", { name: /previous/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /next|load more/i }));
    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it("renders no next/load-more control when hasNext is false", () => {
    render(<OrderList {...baseProps({ hasNext: false })} />);
    expect(screen.queryByRole("button", { name: /next|load more/i })).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<OrderList {...baseProps()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<OrderList {...baseProps()} />);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
