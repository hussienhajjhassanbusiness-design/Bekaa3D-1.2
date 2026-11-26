import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { usePathname } from "next/navigation";
import { useAuth, type AuthContextValue } from "@/lib/auth/AuthProvider";
import { HeaderAccountLink } from "./HeaderAccountLink";

vi.mock("next/navigation", () => ({ usePathname: vi.fn(() => "/") }));
vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));

const mockedUsePathname = vi.mocked(usePathname);
const mockedUseAuth = vi.mocked(useAuth);

function authState(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return { user: null, isAuthenticated: false, isLoading: false, isError: false, logout: vi.fn(), ...overrides };
}

const USER = {
  id: "u1",
  email: "rana@example.com",
  role: "customer",
  emailVerified: true,
  emailVerifiedAt: null,
  createdAt: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  mockedUsePathname.mockReturnValue("/");
  mockedUseAuth.mockReturnValue(authState());
});

describe("HeaderAccountLink", () => {
  it("signed out: Sign in returns the visitor to the page they were on", () => {
    mockedUsePathname.mockReturnValue("/contact");
    render(<HeaderAccountLink variant="bar" />);

    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login?returnTo=%2Fcontact");
  });

  it.each(["/login", "/register", "/forgot-password", "/reset-password", "/verify-email", "/verify-email/resend"])(
    "signed out on the auth page %s: plain /login, never an auth page as returnTo",
    (path) => {
      mockedUsePathname.mockReturnValue(path);
      render(<HeaderAccountLink variant="bar" />);

      expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    }
  );

  it("signed out: marks Sign in as the current page on /login only", () => {
    mockedUsePathname.mockReturnValue("/login");
    const { unmount } = render(<HeaderAccountLink variant="bar" />);
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("aria-current", "page");
    unmount();

    mockedUsePathname.mockReturnValue("/shop");
    render(<HeaderAccountLink variant="bar" />);
    expect(screen.getByRole("link", { name: "Sign in" })).not.toHaveAttribute("aria-current");
  });

  it("an unsafe-looking path is never embedded: the returnTo goes through the shared validator", () => {
    mockedUsePathname.mockReturnValue("//evil.example");
    render(<HeaderAccountLink variant="bar" />);

    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login?returnTo=%2F");
  });

  it("signed in: Account links to /account and marks the account section as current", () => {
    mockedUseAuth.mockReturnValue(authState({ user: USER, isAuthenticated: true }));
    mockedUsePathname.mockReturnValue("/account/orders");
    render(<HeaderAccountLink variant="bar" />);

    const link = screen.getByRole("link", { name: "Account" });
    expect(link).toHaveAttribute("href", "/account");
    expect(link).toHaveAttribute("aria-current", "true");
  });

  it("bar: the label stays in the DOM at every width (visually hidden below 768px), so the name never depends on layout", () => {
    render(<HeaderAccountLink variant="bar" />);

    const label = screen.getByText("Sign in");
    expect(label).toHaveClass("sr-only", "tablet:not-sr-only");
  });

  it("loading: an inert, hidden placeholder in the bar and nothing in the menu", () => {
    mockedUseAuth.mockReturnValue(authState({ isLoading: true }));
    const { container, unmount } = render(<HeaderAccountLink variant="bar" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
    unmount();

    const menu = render(<HeaderAccountLink variant="menu" />);
    expect(menu.container).toBeEmptyDOMElement();
  });

  it("menu: calls onNavigate when followed (closes the sheet)", async () => {
    const onNavigate = vi.fn();
    render(<HeaderAccountLink variant="menu" onNavigate={onNavigate} />);

    const link = screen.getByRole("link", { name: "Sign in" });
    link.addEventListener("click", (event) => event.preventDefault());
    await userEvent.click(link);

    expect(onNavigate).toHaveBeenCalledTimes(1);
  });
});
