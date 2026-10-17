import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppLayout } from "./AppLayout";
import { Header } from "./Header";
import { Footer } from "./Footer";

// The real Header (FVS-022 follow-up: real nav) reads the current route via
// usePathname() — mocked here the same way every other test that renders a
// next/navigation-hook-using component does (ProtectedRoute.test.tsx,
// AccountLayout.test.tsx precedent).
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

describe("AppLayout", () => {
  it("renders exactly one header, one main, and one footer landmark", () => {
    render(
      <AppLayout header={<span>Header</span>} footer={<span>Footer</span>}>
        <p>Content</p>
      </AppLayout>
    );

    expect(screen.getAllByRole("banner")).toHaveLength(1); // native <header>
    expect(screen.getAllByRole("main")).toHaveLength(1); // native <main>
    expect(screen.getAllByRole("contentinfo")).toHaveLength(1); // native <footer>
  });

  it("gives <main> the stable id 'main-content'", () => {
    render(<AppLayout>Content</AppLayout>);

    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("makes <main> programmatically focusable without adding it to the normal tab order (tabIndex=-1, not 0)", () => {
    render(<AppLayout>Content</AppLayout>);

    expect(screen.getByRole("main")).toHaveAttribute("tabindex", "-1");
  });

  it("renders the supplied children inside <main>", () => {
    render(
      <AppLayout>
        <p>Actual page content</p>
      </AppLayout>
    );

    expect(screen.getByRole("main")).toHaveTextContent("Actual page content");
  });

  it("renders header content independently of footer content", () => {
    render(
      <AppLayout header={<span>Header slot content</span>} footer={<span>Footer slot content</span>}>
        Content
      </AppLayout>
    );

    expect(screen.getByRole("banner")).toHaveTextContent("Header slot content");
    expect(screen.getByRole("contentinfo")).toHaveTextContent("Footer slot content");
  });

  it("renders correctly when header/footer content is omitted", () => {
    render(<AppLayout>Content</AppLayout>);

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });

  it("keeps SkipLink as the first tab stop and excludes <main> itself from the tab order", async () => {
    // This is the ordering T05a can actually own: SkipLink precedes whatever
    // content is passed into the header/main/footer slots. It does not (and
    // cannot) prove FVS001-T05b's eventual real header navigation's tab
    // order, since that content doesn't exist yet — re-verify the full,
    // real-content keyboard order once T05b lands.
    const user = userEvent.setup();
    render(
      <AppLayout
        header={<button>Header action</button>}
        footer={<button>Footer action</button>}
      >
        <button>Main action</button>
      </AppLayout>
    );

    await user.tab();
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveFocus();

    await user.tab();
    expect(screen.getByRole("button", { name: "Header action" })).toHaveFocus();

    await user.tab();
    expect(screen.getByRole("button", { name: "Main action" })).toHaveFocus();

    await user.tab();
    expect(screen.getByRole("button", { name: "Footer action" })).toHaveFocus();
  });

  it("composes cleanly with the real Header and Footer (FVS001-T05b): exactly one landmark of each kind, no duplicates", () => {
    render(
      <AppLayout header={<Header />} footer={<Footer />}>
        <p>Page content</p>
      </AppLayout>
    );

    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("contentinfo")).toHaveLength(1);
    expect(screen.getByRole("banner")).toHaveTextContent("Bekaa3D");
    expect(screen.getByRole("contentinfo")).toHaveTextContent("Bekaa3D");
  });

  it("keeps SkipLink as the first tab stop with the real Header/Footer composed in, and main's own content is still reachable by keyboard", async () => {
    // The real Header now has its own navigation (FVS-022 follow-up), so it
    // genuinely contributes tab stops — this no longer asserts SkipLink is
    // immediately followed by main's content, only that SkipLink remains
    // first and that tabbing through the rest of the shell eventually
    // reaches it (keyboard operability, not an exact stop count that would
    // make this test brittle against future nav changes).
    const user = userEvent.setup();
    render(
      <AppLayout header={<Header />} footer={<Footer />}>
        <button>Main action</button>
      </AppLayout>
    );

    await user.tab();
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveFocus();

    const mainActionButton = screen.getByRole("button", { name: "Main action" });
    for (let i = 0; i < 10 && document.activeElement !== mainActionButton; i++) {
      await user.tab();
    }
    expect(mainActionButton).toHaveFocus();
  });
});
