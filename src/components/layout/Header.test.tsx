import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { usePathname } from "next/navigation";
import { useAuth, type AuthContextValue } from "@/lib/auth/AuthProvider";
import { Header } from "./Header";

vi.mock("next/navigation", () => ({ usePathname: vi.fn(() => "/") }));
// The cart link reads the canonical cart query (HeaderCartLink.test.tsx);
// stubbed here so Header stays a layout/navigation test.
vi.mock("./HeaderCartLink", () => ({ HeaderCartLink: () => <a href="/cart">Cart</a> }));
vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));

const mockedUsePathname = vi.mocked(usePathname);
const mockedUseAuth = vi.mocked(useAuth);

function authState(overrides: Partial<AuthContextValue>): AuthContextValue {
  return {
    user: null,
    isAuthenticated: false,
    isLoading: false,
    isError: false,
    logout: vi.fn(),
    ...overrides,
  };
}

const SIGNED_IN = authState({
  user: { id: "u1", email: "rana@example.com", role: "customer", emailVerified: true, emailVerifiedAt: null, createdAt: "2026-01-01T00:00:00Z" },
  isAuthenticated: true,
});

// jsdom has no matchMedia; the open menu listens for the desktop breakpoint.
type ChangeListener = (event: { matches: boolean }) => void;
let mediaListeners: ChangeListener[] = [];

beforeEach(() => {
  mockedUsePathname.mockReturnValue("/");
  mockedUseAuth.mockReturnValue(authState({}));
  mediaListeners = [];
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: (_type: string, listener: ChangeListener) => mediaListeners.push(listener),
    removeEventListener: (_type: string, listener: ChangeListener) => {
      mediaListeners = mediaListeners.filter((l) => l !== listener);
    },
  })) as unknown as typeof window.matchMedia;
});

describe("Header", () => {
  it("renders the brand as a link to / whose accessible name is exactly Bekaa3D", () => {
    render(<Header />);

    const brandLink = screen.getByRole("link", { name: "Bekaa3D" });
    expect(brandLink).toHaveAttribute("href", "/");
  });

  it("uses the real logo mark as a decorative image inside the brand link (the text names the link)", () => {
    render(<Header />);

    const logo = screen.getByRole("link", { name: "Bekaa3D" }).querySelector("img");
    expect(logo).not.toBeNull();
    expect(logo).toHaveAttribute("src", "/brand/bekaa3d-mark.png");
    expect(logo).toHaveAttribute("alt", "");
  });

  it("does not render its own <header> landmark — AppLayout already owns that landmark", () => {
    const { container } = render(<Header />);

    expect(container.querySelector("header")).toBeNull();
  });

  it("renders real navigation links only to mounted routes", () => {
    render(<Header />);

    const nav = screen.getByRole("navigation", { name: "Main" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/", "/shop", "/about", "/bring-your-idea", "/contact"]);
  });

  it("marks the current route's nav link with aria-current", () => {
    mockedUsePathname.mockReturnValue("/shop");
    render(<Header />);

    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Shop" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Home" })).not.toHaveAttribute("aria-current");
  });

  describe("authentication entry", () => {
    it("signed out: a Sign in link to /login carrying the current page as a safe returnTo", () => {
      mockedUsePathname.mockReturnValue("/shop/dragon");
      render(<Header />);

      expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login?returnTo=%2Fshop%2Fdragon");
      expect(screen.queryByRole("link", { name: "Account" })).not.toBeInTheDocument();
    });

    it("signed in: an Account link to /account and no Sign in link", () => {
      mockedUseAuth.mockReturnValue(SIGNED_IN);
      render(<Header />);

      expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute("href", "/account");
      expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
    });

    it("while the session is still resolving, shows neither state (no flash of the wrong one)", () => {
      mockedUseAuth.mockReturnValue(authState({ isLoading: true }));
      render(<Header />);

      expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: "Account" })).not.toBeInTheDocument();
    });

    it("keeps the cart link and follows it with the auth entry in DOM (tab) order", () => {
      render(<Header />);

      const cart = screen.getByRole("link", { name: "Cart" });
      const signIn = screen.getByRole("link", { name: "Sign in" });
      expect(cart.compareDocumentPosition(signIn) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });
  });

  describe("mobile menu", () => {
    it("is closed by default: one Main nav, toggle collapsed and pointing at the sheet's nav", () => {
      render(<Header />);

      const toggle = screen.getByRole("button", { name: "Open menu" });
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(toggle).toHaveAttribute("aria-controls", "mobile-nav");
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(screen.getAllByRole("navigation", { name: "Main" })).toHaveLength(1);
    });

    it("opens a labelled modal sheet with the same links, moves focus into it, and locks page scroll", async () => {
      render(<Header />);
      const toggle = screen.getByRole("button", { name: "Open menu" });

      await userEvent.click(toggle);

      expect(toggle).toHaveAttribute("aria-expanded", "true");
      const dialog = screen.getByRole("dialog", { name: "Menu" });
      expect(dialog).toHaveAttribute("aria-modal", "true");
      const sheetNav = within(dialog).getByRole("navigation", { name: "Main" });
      expect(sheetNav).toHaveAttribute("id", "mobile-nav");
      expect(within(sheetNav).getAllByRole("link").map((l) => l.getAttribute("href"))).toEqual([
        "/",
        "/shop",
        "/about",
        "/bring-your-idea",
        "/contact",
      ]);
      expect(within(dialog).getByRole("button", { name: "Close menu" })).toHaveFocus();
      expect(document.documentElement.style.overflow).toBe("hidden");
    });

    it("represents the auth state inside the sheet (Sign in when signed out, Account when signed in)", async () => {
      const { unmount } = render(<Header />);
      await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
      expect(within(screen.getByRole("dialog")).getByRole("link", { name: "Sign in" })).toHaveAttribute(
        "href",
        "/login?returnTo=%2F"
      );
      unmount();

      mockedUseAuth.mockReturnValue(SIGNED_IN);
      render(<Header />);
      await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
      expect(within(screen.getByRole("dialog")).getByRole("link", { name: "Account" })).toHaveAttribute("href", "/account");
    });

    it("closes with the Close button, returns focus to the toggle and restores page scroll", async () => {
      render(<Header />);
      const toggle = screen.getByRole("button", { name: "Open menu" });
      await userEvent.click(toggle);

      await userEvent.click(screen.getByRole("button", { name: "Close menu" }));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(toggle).toHaveFocus();
      expect(document.documentElement.style.overflow).toBe("");
    });

    it("closes on Escape and returns focus to the toggle", async () => {
      render(<Header />);
      const toggle = screen.getByRole("button", { name: "Open menu" });
      await userEvent.click(toggle);

      await userEvent.keyboard("{Escape}");

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(toggle).toHaveFocus();
    });

    it("traps Tab inside the sheet (wraps from the last control back to the first)", async () => {
      render(<Header />);
      await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
      const dialog = screen.getByRole("dialog");
      const close = within(dialog).getByRole("button", { name: "Close menu" });
      const signIn = within(dialog).getByRole("link", { name: "Sign in" });

      signIn.focus();
      await userEvent.tab();

      expect(close).toHaveFocus();
    });

    it("closes when a menu link is followed", async () => {
      render(<Header />);
      await userEvent.click(screen.getByRole("button", { name: "Open menu" }));

      await userEvent.click(within(screen.getByRole("dialog")).getByRole("link", { name: "Shop" }));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("closes when the route changes by any other means", async () => {
      const { rerender } = render(<Header />);
      await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
      expect(screen.getByRole("dialog")).toBeInTheDocument();

      mockedUsePathname.mockReturnValue("/contact");
      rerender(<Header />);

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("closes when the viewport grows past the desktop breakpoint", async () => {
      render(<Header />);
      await userEvent.click(screen.getByRole("button", { name: "Open menu" }));

      act(() => mediaListeners.forEach((listener) => listener({ matches: true })));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});
