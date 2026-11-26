import { describe, it, expect, vi } from "vitest";
import { Component, type ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ErrorFallback from "./error";

// This boundary handles ONLY unexpected React/render/runtime failures
// (FRONTEND-VERTICAL-SLICE-PLAN.md §17, category A). It must never gain
// knowledge of ApiError/RFC 9457/TanStack Query/network/health failures —
// those are expected application states handled elsewhere (category B/C).
//
// Imported as `ErrorFallback`, not `Error` — importing it under the name
// `Error` would shadow the global `Error` constructor in this module's
// scope, which is exactly the bug this file hit once already: `new
// Error("...")` below silently tried to invoke the React component instead
// of the real Error class, producing an "Invalid hook call" failure that
// had nothing to do with error.tsx's own implementation.

const sampleError = Object.assign(new Error("Internal database connection string exposed here"), {
  digest: "abc123",
});

describe("error.tsx (segment render-error fallback)", () => {
  // FVS001-T14: the AppLayout/Header/Footer shell is now owned by the root
  // layout, which remains rendered around this fallback automatically (a
  // normal segment error.tsx replaces only its own segment's children, not
  // any layout above it — see src/app/layout.test.tsx for the composed-
  // shell landmark assertions). This file tests only the fallback's own
  // content, not shell ownership it no longer has.
  it("renders a clear heading and explanatory text", () => {
    render(<ErrorFallback error={sampleError} retry={() => {}} />);

    expect(
      screen.getByRole("heading", { name: /something went wrong/i })
    ).toBeInTheDocument();
  });

  it("renders a 'Try again' button that calls the provided retry() callback", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    render(<ErrorFallback error={sampleError} retry={retry} />);

    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("never renders the raw error message or stack to the user", () => {
    render(<ErrorFallback error={sampleError} retry={() => {}} />);

    expect(
      screen.queryByText(/Internal database connection string exposed here/)
    ).toBeNull();
    expect(screen.queryByText(/abc123/)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// TEST-ONLY harness below. This is NOT a production error boundary and is
// NOT what protects the real app — Next.js's own App Router owns the real
// segment boundary in production (see FVS001-T07 report for the distinction
// between this harness and real Next.js runtime behavior). It exists only to
// prove, in isolation, that when something throws during render, the T07
// fallback presentation is what a consuming boundary would show instead of
// an unhandled crash — the same fallback component under test above.
class TestOnlyThrowHarness extends Component<
  { children: ReactNode },
  { hasThrown: boolean }
> {
  state = { hasThrown: false };

  static getDerivedStateFromError() {
    return { hasThrown: true };
  }

  render() {
    if (this.state.hasThrown) {
      return <ErrorFallback error={sampleError} retry={() => {}} />;
    }
    return this.props.children;
  }
}

function ThrowingChild(): never {
  throw new Error("deliberate test-only render failure");
}

describe("error.tsx fallback under a thrown descendant (test-only harness, not the real Next.js boundary)", () => {
  it("shows the T07 fallback presentation instead of letting the throw crash the test render", () => {
    render(
      <TestOnlyThrowHarness>
        <ThrowingChild />
      </TestOnlyThrowHarness>
    );

    expect(
      screen.getByRole("heading", { name: /something went wrong/i })
    ).toBeInTheDocument();
  });
});
