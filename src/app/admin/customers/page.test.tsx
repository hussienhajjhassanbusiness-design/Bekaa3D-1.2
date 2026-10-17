import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminCustomersPage from "./page";
import { useAdminUsers } from "@/lib/admin/customers/useAdminUsers";
import type { AdminUserDetail } from "@/lib/admin/customers/customerTypes";

vi.mock("@/lib/admin/customers/useAdminUsers", () => ({ useAdminUsers: vi.fn() }));
const mockedUseAdminUsers = vi.mocked(useAdminUsers);

const CUSTOMER: AdminUserDetail = {
  id: "u1",
  email: "customer@example.com",
  role: "customer",
  is_active: true,
  email_verified_at: "2026-01-01T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
};

function queryResult(overrides: Partial<ReturnType<typeof useAdminUsers>> = {}) {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  } as ReturnType<typeof useAdminUsers>;
}

beforeEach(() => {
  mockedUseAdminUsers.mockReset();
});

describe("AdminCustomersPage", () => {
  it("shows a loading state", () => {
    mockedUseAdminUsers.mockReturnValue(queryResult({ isLoading: true }));
    render(<AdminCustomersPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an empty state", () => {
    mockedUseAdminUsers.mockReturnValue(queryResult({ data: { items: [], next_cursor: null } }));
    render(<AdminCustomersPage />);
    expect(screen.getByText("No customers found.")).toBeInTheDocument();
  });

  it("shows an error state", () => {
    mockedUseAdminUsers.mockReturnValue(
      queryResult({ isError: true, error: { kind: "network", message: "x", raw: undefined } })
    );
    render(<AdminCustomersPage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("renders a row with a status badge and a link to the detail page", () => {
    mockedUseAdminUsers.mockReturnValue(queryResult({ data: { items: [CUSTOMER], next_cursor: null } }));
    render(<AdminCustomersPage />);

    expect(screen.getByText("customer@example.com")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view/i })).toHaveAttribute("href", "/admin/customers/u1");
  });

  it("typing in the search box eventually re-queries with the search term", async () => {
    mockedUseAdminUsers.mockReturnValue(queryResult({ data: { items: [], next_cursor: null } }));
    const user = userEvent.setup();
    render(<AdminCustomersPage />);

    await user.type(screen.getByLabelText(/search by email/i), "cust");

    await vi.waitFor(() => {
      const lastCall = mockedUseAdminUsers.mock.calls.at(-1)?.[0];
      expect(lastCall?.search).toBe("cust");
    });
  });

  it("Next is disabled when there is no next_cursor", () => {
    mockedUseAdminUsers.mockReturnValue(queryResult({ data: { items: [CUSTOMER], next_cursor: null } }));
    render(<AdminCustomersPage />);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("Next is enabled when a next_cursor is present", () => {
    mockedUseAdminUsers.mockReturnValue(queryResult({ data: { items: [CUSTOMER], next_cursor: "cursor-2" } }));
    render(<AdminCustomersPage />);
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });
});
