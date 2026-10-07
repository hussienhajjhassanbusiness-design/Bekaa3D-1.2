import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminTable } from "./AdminTable";

// FVS-009-IMPLEMENTATION-PLAN.md T01 — generic, reusable table shell with
// zero customer-specific knowledge. No sorting seam: the governing plans
// name sorting exactly once, in a test-summary line only (see the plan's
// own §0) — so it is deliberately absent here, not silently added.

interface Row {
  id: string;
  name: string;
}

const ROWS: Row[] = [
  { id: "r-1", name: "Alpha" },
  { id: "r-2", name: "Beta" },
];

const COLUMNS = [
  { header: "Name", render: (row: Row) => row.name },
];

describe("AdminTable", () => {
  it("renders real table semantics", () => {
    render(<AdminTable columns={COLUMNS} rows={ROWS} getRowKey={(row) => row.id} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("gives every column header scope=col", () => {
    render(<AdminTable columns={COLUMNS} rows={ROWS} getRowKey={(row) => row.id} />);
    const header = screen.getByRole("columnheader", { name: "Name" });
    expect(header).toHaveAttribute("scope", "col");
  });

  it("renders each row's cell content via the column's render function", () => {
    render(<AdminTable columns={COLUMNS} rows={ROWS} getRowKey={(row) => row.id} />);
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });

  it("shows a safe empty-state message when there are no rows", () => {
    render(<AdminTable columns={COLUMNS} rows={[]} getRowKey={(row) => row.id} emptyMessage="No customers found." />);
    expect(screen.getByText("No customers found.")).toBeInTheDocument();
  });

  it("shows a loading state instead of rows", () => {
    render(<AdminTable columns={COLUMNS} rows={[]} getRowKey={(row) => row.id} isLoading />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /alpha/i })).not.toBeInTheDocument();
  });

  it("calls onSearchChange when the search input changes, without fetching", async () => {
    const onSearchChange = vi.fn();
    const user = userEvent.setup();
    render(
      <AdminTable
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        searchValue=""
        onSearchChange={onSearchChange}
        searchLabel="Search customers"
      />
    );

    await user.type(screen.getByLabelText("Search customers"), "a");

    expect(onSearchChange).toHaveBeenCalledWith("a");
  });

  it("calls onPrevious when the previous-page control is activated", async () => {
    const onPrevious = vi.fn();
    const user = userEvent.setup();
    render(
      <AdminTable
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        hasPrevious
        hasNext={false}
        onPrevious={onPrevious}
      />
    );

    await user.click(screen.getByRole("button", { name: /previous/i }));

    expect(onPrevious).toHaveBeenCalledTimes(1);
  });

  it("calls onNext when the next-page control is activated", async () => {
    const onNext = vi.fn();
    const user = userEvent.setup();
    render(
      <AdminTable columns={COLUMNS} rows={ROWS} getRowKey={(row) => row.id} hasPrevious={false} hasNext onNext={onNext} />
    );

    await user.click(screen.getByRole("button", { name: /next/i }));

    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it("disables the previous control at the start boundary", () => {
    render(
      <AdminTable columns={COLUMNS} rows={ROWS} getRowKey={(row) => row.id} hasPrevious={false} hasNext onNext={vi.fn()} />
    );
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
  });

  it("disables the next control at the end boundary", () => {
    render(
      <AdminTable
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        hasPrevious
        hasNext={false}
        onPrevious={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: /next/i })).toBeDisabled();
  });

  it("renders row actions as real, keyboard-reachable buttons", async () => {
    const onView = vi.fn();
    const user = userEvent.setup();
    render(
      <AdminTable
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        rowActions={(row) => (
          <button type="button" onClick={() => onView(row.id)}>
            View
          </button>
        )}
      />
    );

    const [firstView] = screen.getAllByRole("button", { name: "View" });
    await user.click(firstView!);

    expect(onView).toHaveBeenCalledWith("r-1");
  });

  it("wraps the table in a horizontal-scroll container instead of dropping columns", () => {
    render(<AdminTable columns={COLUMNS} rows={ROWS} getRowKey={(row) => row.id} />);
    const table = screen.getByRole("table");
    expect(table.parentElement?.className).toMatch(/overflow-x-auto/);
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<AdminTable columns={COLUMNS} rows={ROWS} getRowKey={(row) => row.id} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<AdminTable columns={COLUMNS} rows={ROWS} getRowKey={(row) => row.id} />);
    expect(spy).not.toHaveBeenCalled();
  });
});
