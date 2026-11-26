import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminCustomerDetailPage from "./page";
import { useAdminUser } from "@/lib/admin/customers/useAdminUser";
import { useAdminUserUpdate } from "@/lib/admin/customers/useAdminUserUpdate";
import type { AdminUserDetail } from "@/lib/admin/customers/customerTypes";

vi.mock("@/lib/admin/customers/useAdminUser", () => ({ useAdminUser: vi.fn() }));
vi.mock("@/lib/admin/customers/useAdminUserUpdate", () => ({ useAdminUserUpdate: vi.fn() }));
vi.mock("next/navigation", () => ({ useParams: () => ({ id: "u1" }) }));

const mockedUseAdminUser = vi.mocked(useAdminUser);
const mockedUseAdminUserUpdate = vi.mocked(useAdminUserUpdate);

const ACTIVE_CUSTOMER: AdminUserDetail = {
  id: "u1",
  email: "customer@example.com",
  role: "customer",
  is_active: true,
  email_verified_at: "2026-01-01T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
};

function queryResult(overrides: Partial<ReturnType<typeof useAdminUser>> = {}) {
  return { data: undefined, isLoading: false, isError: false, error: null, ...overrides } as ReturnType<
    typeof useAdminUser
  >;
}

beforeEach(() => {
  mockedUseAdminUser.mockReset();
  mockedUseAdminUserUpdate.mockReset();
  mockedUseAdminUserUpdate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
});

describe("AdminCustomerDetailPage", () => {
  it("shows a loading state", () => {
    mockedUseAdminUser.mockReturnValue(queryResult({ isLoading: true }));
    render(<AdminCustomerDetailPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows real not-found UX for a 404 (no admin-specific wording)", () => {
    mockedUseAdminUser.mockReturnValue(
      queryResult({ isError: true, error: { kind: "http", status: 404, code: "NOT_FOUND", message: "x", raw: undefined } })
    );
    render(<AdminCustomerDetailPage />);
    expect(screen.getByText(/page not found/i)).toBeInTheDocument();
  });

  it("shows a retryable error for a transport failure, not not-found", () => {
    mockedUseAdminUser.mockReturnValue(queryResult({ isError: true, error: { kind: "network", message: "x", raw: undefined } }));
    render(<AdminCustomerDetailPage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(/page not found/i)).not.toBeInTheDocument();
  });

  it("renders the customer's email, status, role, and join date", () => {
    mockedUseAdminUser.mockReturnValue(queryResult({ data: ACTIVE_CUSTOMER }));
    render(<AdminCustomerDetailPage />);
    expect(screen.getByRole("heading", { name: "customer@example.com" })).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("customer")).toBeInTheDocument();
  });

  it("deactivating an active customer requires confirmation, then calls the mutation", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseAdminUserUpdate.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedUseAdminUser.mockReturnValue(queryResult({ data: ACTIVE_CUSTOMER }));
    const user = userEvent.setup();
    render(<AdminCustomerDetailPage />);

    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/revokes all of this customer's active sessions/i)).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Deactivate" }).at(-1)!);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ userId: "u1", isActive: false }));
  });

  it("only is_active is ever sent — reactivating a deactivated customer", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseAdminUserUpdate.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedUseAdminUser.mockReturnValue(queryResult({ data: { ...ACTIVE_CUSTOMER, is_active: false } }));
    const user = userEvent.setup();
    render(<AdminCustomerDetailPage />);

    await user.click(screen.getByRole("button", { name: "Reactivate" }));
    await user.click(screen.getAllByRole("button", { name: "Reactivate" }).at(-1)!);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ userId: "u1", isActive: true }));
    expect(mutateAsync.mock.calls[0]![0]).toEqual({ userId: "u1", isActive: true });
  });

  it("cancelling the confirm dialog never calls the mutation", async () => {
    const mutateAsync = vi.fn();
    mockedUseAdminUserUpdate.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedUseAdminUser.mockReturnValue(queryResult({ data: ACTIVE_CUSTOMER }));
    const user = userEvent.setup();
    render(<AdminCustomerDetailPage />);

    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(mutateAsync).not.toHaveBeenCalled();
  });
});
