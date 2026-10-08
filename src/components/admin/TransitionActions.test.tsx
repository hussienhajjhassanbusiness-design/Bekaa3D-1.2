import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TransitionActions } from "./TransitionActions";
import type { TransitionAffordance } from "@/lib/admin/adminOrderModel";

// FVS-030-IMPLEMENTATION-PLAN.md T04 — renders exactly the supplied
// legal actions, never a locally-invented "Next". requiresConfirmation
// reuses the existing ConfirmDialog, no second focus trap. All
// buttons disable while any action is pending -- never an optimistic
// status mutation (this component has no status field to mutate at
// all, structurally).

const ACTIONS: readonly TransitionAffordance[] = [
  { id: "move-to-production", label: "Move to production", requiresConfirmation: false },
  { id: "mark-delivered", label: "Mark delivered", requiresConfirmation: true },
];

describe("TransitionActions", () => {
  it("renders exactly one button per supplied action, using that action's own label", () => {
    render(<TransitionActions actions={ACTIONS} onSelectAction={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Move to production" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark delivered" })).toBeInTheDocument();
  });

  it("renders nothing when actions is empty — never a locally-invented 'Next' fallback", () => {
    render(<TransitionActions actions={[]} onSelectAction={vi.fn()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("an action with requiresConfirmation: false calls onSelectAction immediately on click", async () => {
    const onSelectAction = vi.fn();
    const user = userEvent.setup();
    render(<TransitionActions actions={ACTIONS} onSelectAction={onSelectAction} />);

    await user.click(screen.getByRole("button", { name: "Move to production" }));

    expect(onSelectAction).toHaveBeenCalledWith("move-to-production");
  });

  it("an action with requiresConfirmation: true opens ConfirmDialog first, never firing onSelectAction on the initial click", async () => {
    const onSelectAction = vi.fn();
    const user = userEvent.setup();
    render(<TransitionActions actions={ACTIONS} onSelectAction={onSelectAction} />);

    await user.click(screen.getByRole("button", { name: "Mark delivered" }));

    expect(onSelectAction).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("confirming the dialog calls onSelectAction; cancelling never does", async () => {
    const onSelectAction = vi.fn();
    const user = userEvent.setup();
    render(<TransitionActions actions={ACTIONS} onSelectAction={onSelectAction} />);

    await user.click(screen.getByRole("button", { name: "Mark delivered" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onSelectAction).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Mark delivered" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onSelectAction).toHaveBeenCalledWith("mark-delivered");
  });

  it("disables all action buttons while pendingActionId is set", () => {
    render(<TransitionActions actions={ACTIONS} onSelectAction={vi.fn()} pendingActionId="move-to-production" />);
    expect(screen.getByRole("button", { name: "Move to production" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Mark delivered" })).toBeDisabled();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<TransitionActions actions={ACTIONS} onSelectAction={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
