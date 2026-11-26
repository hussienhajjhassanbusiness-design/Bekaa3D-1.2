import { describe, it, expect } from "vitest";
import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import { AuthBackToLogin, AuthCard, AuthShell } from "./AuthShell";

// Batch 4 — the shared auth presentation. Presentation only: these tests pin
// the accessibility contract (one h1, focus target on request, decorative
// brand / glyph) rather than classes.
describe("AuthShell / AuthCard", () => {
  it("renders exactly one level-1 heading with the given title, plus description, body and footer", () => {
    render(
      <AuthShell title="Log in" description="Welcome back." footer={<span>Footer strip</span>}>
        <p>Body content</p>
      </AuthShell>
    );

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Log in" })).toBeInTheDocument();
    expect(screen.getByText("Welcome back.")).toBeInTheDocument();
    expect(screen.getByText("Body content")).toBeInTheDocument();
    expect(screen.getByText("Footer strip")).toBeInTheDocument();
  });

  it("makes the heading a programmatic-only focus target only when a titleRef is passed", () => {
    const ref = createRef<HTMLHeadingElement>();
    const { rerender } = render(<AuthCard title="Reset your password" titleRef={ref} />);

    const heading = screen.getByRole("heading", { level: 1 });
    expect(ref.current).toBe(heading);
    expect(heading).toHaveAttribute("tabindex", "-1");

    rerender(<AuthCard title="Reset your password" />);
    expect(screen.getByRole("heading", { level: 1 })).not.toHaveAttribute("tabindex");
  });

  it("keeps the brand wordmark and the status glyph out of the accessibility tree", () => {
    const { container } = render(<AuthCard title="Verify your email" showBrand status={{ icon: "verified", tone: "success" }} />);

    // The heading's accessible name is only the title: nothing decorative leaks in.
    expect(screen.getByRole("heading", { level: 1 })).toHaveAccessibleName("Verify your email");
    expect(container.querySelector('[aria-hidden="true"]')?.textContent).toBe("Bekaa3D");
    expect(container.querySelector('svg[data-icon="verified"]')).toHaveAttribute("aria-hidden", "true");
  });

  it("owns no form, input or live region of its own", () => {
    const { container } = render(<AuthShell title="Log in" showBrand footer="x" />);

    expect(container.querySelector("form, input, button")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("AuthBackToLogin links to /login", () => {
    render(<AuthBackToLogin />);
    expect(screen.getByRole("link", { name: /back to log in/i })).toHaveAttribute("href", "/login");
  });
});
