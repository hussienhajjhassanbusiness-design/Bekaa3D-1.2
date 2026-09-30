import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useFormContext } from "react-hook-form";
import { z } from "zod";
import { Form } from "./Form";
import { Button } from "./Button";

// FVS002-T05 — Form's own tests use a FAKE local schema only, never a real
// registration/resend schema (those don't exist yet — contract-gated,
// FVS-002-IMPLEMENTATION-PLAN.md §1). FakeField is a test-only bridge
// proving Form's React Hook Form context is genuinely usable by a
// descendant via useFormContext — it is not a deliverable of this task;
// real field-to-RHF wiring happens inside the contract-gated page tasks.

const fakeSchema = z.object({
  name: z.string().min(1, "Name is required"),
});
type FakeValues = z.infer<typeof fakeSchema>;

function FakeField() {
  const {
    register,
    formState: { errors },
  } = useFormContext<FakeValues>();
  return (
    <div>
      <label htmlFor="name">Name</label>
      <input id="name" {...register("name")} />
      {errors.name && <span>{errors.name.message}</span>}
    </div>
  );
}

function renderTestForm(onSubmit: (values: FakeValues) => void | Promise<void>) {
  return render(
    <Form schema={fakeSchema} defaultValues={{ name: "" }} onSubmit={onSubmit}>
      <FakeField />
      <Button type="submit">Submit</Button>
    </Form>
  );
}

describe("Form", () => {
  it("renders a semantic <form> containing its children", () => {
    renderTestForm(vi.fn());

    expect(document.querySelector("form")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit" })).toBeInTheDocument();
  });

  it("calls onSubmit with parsed values on a valid submit", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderTestForm(onSubmit);

    await user.type(screen.getByLabelText("Name"), "Ada");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ name: "Ada" }, expect.anything()));
  });

  it("does not call onSubmit on an invalid submit, and renders a polite error summary", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderTestForm(onSubmit);

    await user.click(screen.getByRole("button", { name: "Submit" }));

    const summary = await screen.findByRole("status");
    expect(onSubmit).not.toHaveBeenCalled();
    expect(summary).toHaveAttribute("aria-live", "polite");
    expect(within(summary).getByText("Name is required")).toBeInTheDocument();
  });

  it("moves focus to the first invalid field on a failed submit", async () => {
    const user = userEvent.setup();
    renderTestForm(vi.fn());

    await user.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => expect(screen.getByLabelText("Name")).toHaveFocus());
  });

  it("prevents a double submission from firing onSubmit twice", async () => {
    const user = userEvent.setup();
    let resolveSubmit!: () => void;
    const onSubmit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveSubmit = resolve;
        })
    );
    renderTestForm(onSubmit);

    await user.type(screen.getByLabelText("Name"), "Ada");
    const submitButton = screen.getByRole("button", { name: "Submit" });

    await user.click(submitButton);
    await user.click(submitButton); // fired while the first submission is still in flight

    resolveSubmit();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  });

  it("disables the submit button while submitting", async () => {
    const user = userEvent.setup();
    let resolveSubmit!: () => void;
    const onSubmit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveSubmit = resolve;
        })
    );
    renderTestForm(onSubmit);

    await user.type(screen.getByLabelText("Name"), "Ada");
    const submitButton = screen.getByRole("button", { name: "Submit" });
    await user.click(submitButton);

    await waitFor(() => expect(screen.getByRole("button", { name: "Submit" })).toBeDisabled());
    resolveSubmit();
  });
});
