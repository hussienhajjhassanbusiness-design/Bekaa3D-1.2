import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LogoutButton } from "./LogoutButton";
import { useAuth, type AuthContextValue } from "@/lib/auth/AuthProvider";

// Phase 5A defect 7: AuthProvider.logout() existed but no mounted UI
// called it. LogoutButton is the one shared control both the account and
// admin shells mount. It owns no logout logic of its own: useLogout's
// local-first clear / server call / bounded retry is proven in
// useLogout.test.ts; this proves the control calls it and leaves to /login.

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
const mockedUseAuth = vi.mocked(useAuth);

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

function authState(logout: AuthContextValue["logout"]): AuthContextValue {
  return { user: null, isAuthenticated: true, isLoading: false, isError: false, logout };
}

beforeEach(() => {
  mockedUseAuth.mockReset();
  replace.mockReset();
});

describe("LogoutButton", () => {
  it("renders an accessible 'Log out' button", () => {
    mockedUseAuth.mockReturnValue(authState(vi.fn().mockResolvedValue({ serverConfirmed: true })));
    render(<LogoutButton />);
    expect(screen.getByRole("button", { name: "Log out" })).toBeEnabled();
  });

  it("calls the shared logout() exactly once, then replaces the route with /login", async () => {
    const logout = vi.fn().mockResolvedValue({ serverConfirmed: true });
    mockedUseAuth.mockReturnValue(authState(logout));
    render(<LogoutButton />);

    await userEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(logout).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("still leaves to /login when the server could not confirm (frontend is already logged out locally)", async () => {
    const logout = vi.fn().mockResolvedValue({ serverConfirmed: false });
    mockedUseAuth.mockReturnValue(authState(logout));
    render(<LogoutButton />);

    await userEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("is disabled while logging out, so a double click sends one logout", async () => {
    let resolve!: (v: { serverConfirmed: boolean }) => void;
    const logout = vi.fn(() => new Promise<{ serverConfirmed: boolean }>((r) => (resolve = r)));
    mockedUseAuth.mockReturnValue(authState(logout));
    render(<LogoutButton />);

    const button = screen.getByRole("button", { name: "Log out" });
    await userEvent.click(button);
    expect(screen.getByRole("button", { name: /log(ging)? out/i })).toBeDisabled();
    await userEvent.click(button);
    expect(logout).toHaveBeenCalledTimes(1);

    resolve({ serverConfirmed: true });
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
