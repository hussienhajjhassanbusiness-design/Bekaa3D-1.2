import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EntitlementList } from "./EntitlementList";
import type { EntitlementModel } from "@/lib/entitlements/entitlementModel";

// FVS-020-IMPLEMENTATION-PLAN.md T03 — presentational only, no
// network, no query. The backend excludes revoked entitlements from
// the list endpoint entirely (VS-017's own rule) — so there is no
// revoked badge/branch/filter to build here at all, proven below by
// asserting the word never appears, rather than constructing a fake
// revoked input and hiding it client-side.

const ENTITLEMENTS: EntitlementModel[] = [
  { id: "ent-1", productDisplayName: "Dragon STL", currentVersionLabel: "Version 3" },
  { id: "ent-2", productDisplayName: "Castle STL", currentVersionLabel: "Version 1" },
];

describe("EntitlementList", () => {
  it("shows a loading state", () => {
    render(<EntitlementList entitlements={[]} isLoading />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows a safe error message", () => {
    render(<EntitlementList entitlements={[]} isError errorMessage="We couldn't load your library." />);
    expect(screen.getByText("We couldn't load your library.")).toBeInTheDocument();
  });

  it("retry calls the provided callback", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<EntitlementList entitlements={[]} isError errorMessage="Failed." onRetry={onRetry} />);

    await user.click(screen.getByRole("button", { name: /retry/i }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows a safe empty-library message with a browse-shop action", async () => {
    const onBrowseShop = vi.fn();
    const user = userEvent.setup();
    render(<EntitlementList entitlements={[]} onBrowseShop={onBrowseShop} />);

    expect(screen.getByText(/don't own any stl products yet/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /browse/i }));

    expect(onBrowseShop).toHaveBeenCalledTimes(1);
  });

  it("renders a real semantic list when populated", () => {
    render(<EntitlementList entitlements={ENTITLEMENTS} />);
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("renders every entitlement's product name", () => {
    render(<EntitlementList entitlements={ENTITLEMENTS} />);
    expect(screen.getByText("Dragon STL")).toBeInTheDocument();
    expect(screen.getByText("Castle STL")).toBeInTheDocument();
  });

  it("passes each entitlement into the supplied renderActionSlot seam", () => {
    const renderActionSlot = vi.fn((entitlement: EntitlementModel) => (
      <a href={`/x/${entitlement.id}`}>Download {entitlement.productDisplayName}</a>
    ));
    render(<EntitlementList entitlements={ENTITLEMENTS} renderActionSlot={renderActionSlot} />);

    expect(screen.getByRole("link", { name: "Download Dragon STL" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download Castle STL" })).toBeInTheDocument();
  });

  it("has a responsive grid/stacked layout structure (grid on larger widths, single column on mobile)", () => {
    render(<EntitlementList entitlements={ENTITLEMENTS} />);
    const list = screen.getByRole("list");
    expect(list.className).toMatch(/grid-cols-1/);
    expect(list.className).toMatch(/tablet:grid-cols-/);
  });

  it("never renders any revoked badge/branch/filter — the API never returns revoked rows to begin with", () => {
    render(<EntitlementList entitlements={ENTITLEMENTS} />);
    expect(screen.queryByText(/revoked/i)).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<EntitlementList entitlements={ENTITLEMENTS} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<EntitlementList entitlements={ENTITLEMENTS} />);
    expect(spy).not.toHaveBeenCalled();
  });
});
