import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GrantEntitlementDialog } from "./GrantEntitlementDialog";
import type { CustomerOption, ProductOption } from "@/lib/admin/entitlementGrantModels";

// FVS-019-IMPLEMENTATION-PLAN.md T03 — presentational only, no network,
// no query. Composes the shared DialogShell (not a second focus-trap
// implementation) and SearchableCombobox. Supports a preselected
// customer/product fixed by context (customer-detail vs product-detail
// entry points) without forcing the caller to re-select something
// already known. Physical products are never selectable — client-side
// UX only, the server remains the real authority
// (#SECURITY-ENTITLEMENT-GRANT).

const CUSTOMERS: CustomerOption[] = [
  { id: "cust-1", displayLabel: "Ada Lovelace" },
  { id: "cust-2", displayLabel: "Grace Hopper" },
];

const PRODUCTS: ProductOption[] = [
  { id: "prod-1", displayLabel: "Dragon STL", productType: "stl" },
  { id: "prod-2", displayLabel: "Printed Vase", productType: "physical" },
];

describe("GrantEntitlementDialog", () => {
  it("renders a real, accessible dialog via the shared DialogShell", () => {
    render(
      <GrantEntitlementDialog
        open={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        customerOptions={CUSTOMERS}
        productOptions={PRODUCTS}
      />
    );
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  });

  it("closes via Escape, reusing the shared shell's behavior", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <GrantEntitlementDialog open={true} onClose={onClose} onConfirm={vi.fn()} customerOptions={CUSTOMERS} productOptions={PRODUCTS} />
    );

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders a labeled customer picker when no customer is fixed by context", () => {
    render(
      <GrantEntitlementDialog open={true} onClose={vi.fn()} onConfirm={vi.fn()} customerOptions={CUSTOMERS} productOptions={PRODUCTS} />
    );
    expect(screen.getByLabelText(/customer/i)).toBeInTheDocument();
  });

  it("renders a labeled product picker containing only STL products, never physical ones", async () => {
    const user = userEvent.setup();
    render(
      <GrantEntitlementDialog open={true} onClose={vi.fn()} onConfirm={vi.fn()} customerOptions={CUSTOMERS} productOptions={PRODUCTS} />
    );

    await user.click(screen.getByLabelText(/product/i));

    expect(screen.getByRole("option", { name: "Dragon STL" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Printed Vase" })).not.toBeInTheDocument();
  });

  it("known-customer mode shows the customer as static text with no customer picker", () => {
    render(
      <GrantEntitlementDialog
        open={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        fixedCustomer={CUSTOMERS[0]}
        productOptions={PRODUCTS}
      />
    );
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.queryByLabelText(/^customer$/i)).not.toBeInTheDocument();
  });

  it("known-product mode shows the product as static text with no product picker", () => {
    render(
      <GrantEntitlementDialog
        open={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        customerOptions={CUSTOMERS}
        fixedProduct={PRODUCTS[0]}
      />
    );
    expect(screen.getByText("Dragon STL")).toBeInTheDocument();
    expect(screen.queryByLabelText(/product/i)).not.toBeInTheDocument();
  });

  it("disables Grant until both a customer and an STL product are resolved", () => {
    render(
      <GrantEntitlementDialog open={true} onClose={vi.fn()} onConfirm={vi.fn()} customerOptions={CUSTOMERS} productOptions={PRODUCTS} />
    );
    expect(screen.getByRole("button", { name: /grant/i })).toBeDisabled();
  });

  it("enables Grant once a customer and STL product are both selected", async () => {
    const user = userEvent.setup();
    render(
      <GrantEntitlementDialog open={true} onClose={vi.fn()} onConfirm={vi.fn()} customerOptions={CUSTOMERS} productOptions={PRODUCTS} />
    );

    await user.click(screen.getByLabelText(/customer/i));
    await user.keyboard("{ArrowDown}{Enter}");
    await user.click(screen.getByLabelText(/product/i));
    await user.keyboard("{ArrowDown}{Enter}");

    expect(screen.getByRole("button", { name: /grant/i })).not.toBeDisabled();
  });

  it("calls onConfirm with the exact normalized customer and product ids", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <GrantEntitlementDialog open={true} onClose={vi.fn()} onConfirm={onConfirm} customerOptions={CUSTOMERS} productOptions={PRODUCTS} />
    );

    await user.click(screen.getByLabelText(/customer/i));
    await user.keyboard("{ArrowDown}{Enter}");
    await user.click(screen.getByLabelText(/product/i));
    await user.keyboard("{ArrowDown}{Enter}");
    await user.click(screen.getByRole("button", { name: /grant/i }));

    expect(onConfirm).toHaveBeenCalledWith("cust-1", "prod-1");
  });

  it("disables Grant and Cancel while isSubmitting", () => {
    render(
      <GrantEntitlementDialog
        open={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        fixedCustomer={CUSTOMERS[0]}
        fixedProduct={PRODUCTS[0]}
        isSubmitting
      />
    );
    expect(screen.getByRole("button", { name: /grant/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();
  });

  it("renders a caller-supplied safe error message, never a raw backend object", () => {
    render(
      <GrantEntitlementDialog
        open={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        customerOptions={CUSTOMERS}
        productOptions={PRODUCTS}
        errorMessage="This customer already owns this product."
      />
    );
    expect(screen.getByText("This customer already owns this product.")).toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(
      <GrantEntitlementDialog open={true} onClose={vi.fn()} onConfirm={vi.fn()} customerOptions={CUSTOMERS} productOptions={PRODUCTS} />
    );
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(
      <GrantEntitlementDialog open={true} onClose={vi.fn()} onConfirm={vi.fn()} customerOptions={CUSTOMERS} productOptions={PRODUCTS} />
    );
    expect(spy).not.toHaveBeenCalled();
  });
});
