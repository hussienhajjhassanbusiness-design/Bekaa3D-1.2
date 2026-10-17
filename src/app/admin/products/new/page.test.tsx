import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminNewProductPage from "./page";
import { useAdminProductCreate } from "@/lib/admin/products/useAdminProductMutations";
import { useProductFormReferenceData } from "@/lib/admin/products/useProductFormReferenceData";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mockPush }) }));
vi.mock("@/lib/admin/products/useAdminProductMutations", () => ({ useAdminProductCreate: vi.fn() }));
vi.mock("@/lib/admin/products/useProductFormReferenceData", () => ({ useProductFormReferenceData: vi.fn() }));

const mockedUseAdminProductCreate = vi.mocked(useAdminProductCreate);
const mockedUseProductFormReferenceData = vi.mocked(useProductFormReferenceData);

beforeEach(() => {
  mockPush.mockReset();
  mockedUseAdminProductCreate.mockReset();
  mockedUseProductFormReferenceData.mockReset();
  mockedUseProductFormReferenceData.mockReturnValue({
    categories: [{ id: "cat1", name: "Toys" }],
    materials: [{ id: "mat1", name: "PLA" }],
    colours: [{ id: "col1", name: "Red" }],
    isLoading: false,
  });
});

async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Name"), "Moon Lamp");
  await user.type(screen.getByLabelText("Slug"), "moon-lamp");
  await user.selectOptions(screen.getByLabelText("Category"), "cat1");
  await user.type(screen.getByLabelText(/price/i), "18.00");
  await user.type(screen.getByLabelText("Production lead time (days)"), "2");
  await user.type(screen.getByLabelText("Batch size"), "2");
  await user.type(screen.getByLabelText("Max quantity per order line"), "5");
}

describe("AdminNewProductPage", () => {
  it("blocks submission and shows field errors when required fields are missing", async () => {
    mockedUseAdminProductCreate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
    const user = userEvent.setup();
    render(<AdminNewProductPage />);

    await user.click(screen.getByRole("button", { name: /create product/i }));

    expect(screen.getByText("Name is required.")).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("creates a physical product with cents-safe pricing and navigates to its edit page", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ id: "p1" });
    mockedUseAdminProductCreate.mockReturnValue({ mutateAsync, isPending: false } as never);
    const user = userEvent.setup();
    render(<AdminNewProductPage />);

    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /create product/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const body = mutateAsync.mock.calls[0]![0] as Record<string, unknown>;
    expect(body.price).toEqual({ amount_cents: 1800, currency: "USD" });
    expect(body.type).toBe("physical");

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/admin/products/p1/edit"));
  });

  it("never sends physical-only fields when creating an STL product", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ id: "p2" });
    mockedUseAdminProductCreate.mockReturnValue({ mutateAsync, isPending: false } as never);
    const user = userEvent.setup();
    render(<AdminNewProductPage />);

    await user.click(screen.getByLabelText(/stl/i));
    await user.type(screen.getByLabelText("Name"), "Dragon STL");
    await user.type(screen.getByLabelText("Slug"), "dragon-stl");
    await user.selectOptions(screen.getByLabelText("Category"), "cat1");
    await user.type(screen.getByLabelText(/price/i), "7.00");
    await user.click(screen.getByRole("button", { name: /create product/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const body = mutateAsync.mock.calls[0]![0] as Record<string, unknown>;
    expect(body).not.toHaveProperty("purchase_mode");
    expect(body).not.toHaveProperty("dimensions");
  });

  it("shows a SLUG_CONFLICT error inline on the slug field, not a generic banner", async () => {
    const mutateAsync = vi.fn().mockRejectedValue({ kind: "http", status: 409, code: "SLUG_CONFLICT", message: "x", raw: undefined });
    mockedUseAdminProductCreate.mockReturnValue({ mutateAsync, isPending: false } as never);
    const user = userEvent.setup();
    render(<AdminNewProductPage />);

    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /create product/i }));

    expect(await screen.findByText("That slug is already in use by another live product.")).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });
});
