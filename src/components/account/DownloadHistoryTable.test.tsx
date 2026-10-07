import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DownloadHistoryTable } from "./DownloadHistoryTable";
import type { DownloadHistoryItem } from "@/lib/entitlements/downloadHistoryModel";

// FVS-021-IMPLEMENTATION-PLAN.md T03 — presentational only, no
// network, no query, no fabricated pagination (history's pagination
// status is unconfirmed). Desktop/tablet renders a real <table>;
// mobile renders a stacked list — both exist in the DOM simultaneously
// with CSS-only visibility switching (no JS viewport detection), so
// one of the two is always `hidden` (display:none, removed from the
// accessibility tree) to avoid duplicate screen-reader announcements.

const ITEMS: DownloadHistoryItem[] = [
  { id: "dl-1", productDisplayName: "Dragon STL", dateLabel: "Oct 7, 2026" },
  { id: "dl-2", productDisplayName: "Castle STL", dateLabel: "Oct 5, 2026" },
];

describe("DownloadHistoryTable", () => {
  it("shows a loading state", () => {
    render(<DownloadHistoryTable items={[]} isLoading />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows a safe error message", () => {
    render(<DownloadHistoryTable items={[]} isError errorMessage="We couldn't load your download history." />);
    expect(screen.getByText("We couldn't load your download history.")).toBeInTheDocument();
  });

  it("retry calls the provided callback", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<DownloadHistoryTable items={[]} isError errorMessage="Failed." onRetry={onRetry} />);

    await user.click(screen.getByRole("button", { name: /retry/i }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows a safe empty-history message", () => {
    render(<DownloadHistoryTable items={[]} />);
    expect(screen.getByText(/haven't downloaded/i)).toBeInTheDocument();
  });

  it("renders a real desktop table with scoped column headers", () => {
    render(<DownloadHistoryTable items={ITEMS} />);
    const table = screen.getByRole("table", { hidden: true });
    expect(table).toBeInTheDocument();
    const headers = screen.getAllByRole("columnheader", { hidden: true });
    expect(headers.length).toBeGreaterThanOrEqual(2);
    for (const header of headers) {
      expect(header).toHaveAttribute("scope", "col");
    }
  });

  it("renders every item's product name and date label", () => {
    render(<DownloadHistoryTable items={ITEMS} />);
    expect(screen.getAllByText("Dragon STL").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Oct 7, 2026").length).toBeGreaterThan(0);
  });

  it("the desktop table is CSS-hidden on narrow widths (not JS viewport detection)", () => {
    render(<DownloadHistoryTable items={ITEMS} />);
    const table = screen.getByRole("table", { hidden: true });
    expect(table.className).toMatch(/hidden/);
    expect(table.className).toMatch(/tablet:table/);
  });

  it("renders a mobile stacked list representation that is CSS-hidden at tablet and above", () => {
    render(<DownloadHistoryTable items={ITEMS} />);
    const lists = screen.getAllByRole("list", { hidden: true });
    const mobileList = lists.find((list) => list.className.includes("tablet:hidden"));
    expect(mobileList).toBeTruthy();
  });

  it("fabricates no pagination controls", () => {
    render(<DownloadHistoryTable items={ITEMS} />);
    expect(screen.queryByRole("button", { name: /next|previous|page/i })).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<DownloadHistoryTable items={ITEMS} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<DownloadHistoryTable items={ITEMS} />);
    expect(spy).not.toHaveBeenCalled();
  });
});
