import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToastProvider, useToast } from "./ToastProvider";
import type { ToastVariant } from "./Toast";

// FVS001-T12 — a test-only trigger, never a real business event. Nothing in
// FVS-001 wires Toast to a real event (§17); this exists solely to exercise
// useToast() from a descendant component.
function ShowToastTrigger({ message, variant }: { message: string; variant: ToastVariant }) {
  const { showToast } = useToast();
  return (
    <button type="button" onClick={() => showToast({ message, variant })}>
      show: {message}
    </button>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ToastProvider / useToast", () => {
  it("lets a descendant call useToast() without crashing", () => {
    render(
      <ToastProvider>
        <ShowToastTrigger message="hello" variant="info" />
      </ToastProvider>
    );

    expect(screen.getByRole("button", { name: "show: hello" })).toBeInTheDocument();
  });

  it("renders a toast with the correct message and variant after showToast() is called", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <ShowToastTrigger message="Saved successfully" variant="success" />
      </ToastProvider>
    );

    await user.click(screen.getByRole("button", { name: "show: Saved successfully" }));

    const toast = screen.getByRole("status");
    expect(toast).toHaveTextContent("Saved successfully");
    expect(toast).toHaveAttribute("data-variant", "success");
  });

  it("dismisses a shown toast when its dismiss control is activated", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <ShowToastTrigger message="Dismiss me" variant="error" />
      </ToastProvider>
    );

    await user.click(screen.getByRole("button", { name: "show: Dismiss me" }));
    expect(screen.getByRole("status")).toHaveTextContent("Dismiss me");

    await user.click(screen.getByRole("button", { name: "Dismiss notification" }));

    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows more than one toast at once without crashing", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <ShowToastTrigger message="First toast" variant="success" />
        <ShowToastTrigger message="Second toast" variant="info" />
      </ToastProvider>
    );

    await user.click(screen.getByRole("button", { name: "show: First toast" }));
    await user.click(screen.getByRole("button", { name: "show: Second toast" }));

    const toasts = screen.getAllByRole("status");
    expect(toasts).toHaveLength(2);
    expect(screen.getByText("First toast")).toBeInTheDocument();
    expect(screen.getByText("Second toast")).toBeInTheDocument();
  });

  it("dismissing one toast does not remove the other", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <ShowToastTrigger message="Keep me" variant="success" />
        <ShowToastTrigger message="Remove me" variant="error" />
      </ToastProvider>
    );

    await user.click(screen.getByRole("button", { name: "show: Keep me" }));
    await user.click(screen.getByRole("button", { name: "show: Remove me" }));

    const removeToast = screen.getByText("Remove me").closest('[role="status"]');
    expect(removeToast).not.toBeNull();
    const dismissButton = within(removeToast as HTMLElement).getByRole("button", { name: "Dismiss notification" });
    await user.click(dismissButton);

    expect(screen.queryByText("Remove me")).toBeNull();
    expect(screen.getByText("Keep me")).toBeInTheDocument();
  });

  it("throws a clear developer error when useToast() is called outside a ToastProvider", () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    function LoneConsumer() {
      useToast();
      return null;
    }

    expect(() => render(<LoneConsumer />)).toThrow("useToast must be used within a ToastProvider");

    consoleErrorSpy.mockRestore();
  });
});
