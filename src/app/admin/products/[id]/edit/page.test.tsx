import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminProductEditPage from "./page";
import { useAdminProduct } from "@/lib/admin/products/useAdminProduct";
import { useAdminProductUpdate } from "@/lib/admin/products/useAdminProductMutations";
import { useProductFormReferenceData } from "@/lib/admin/products/useProductFormReferenceData";
import {
  useProductImageUpload,
  useProductImageAltTextUpdate,
  useProductImageSetCover,
  useProductImageReorder,
  useProductImageDelete,
} from "@/lib/admin/products/useProductImageMutations";
import type { RawAdminProductDetail } from "@/lib/admin/products/productAdminTypes";

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "p1" }) }));
vi.mock("@/lib/admin/products/useAdminProduct", () => ({ useAdminProduct: vi.fn() }));
vi.mock("@/lib/admin/products/useAdminProductMutations", () => ({
  useAdminProductUpdate: vi.fn(),
  useAdminProductCreate: vi.fn(),
  useAdminProductDelete: vi.fn(),
}));
vi.mock("@/lib/admin/products/useProductFormReferenceData", () => ({ useProductFormReferenceData: vi.fn() }));
vi.mock("@/lib/admin/products/useProductImageMutations", () => ({
  useProductImageUpload: vi.fn(),
  useProductImageAltTextUpdate: vi.fn(),
  useProductImageSetCover: vi.fn(),
  useProductImageReorder: vi.fn(),
  useProductImageDelete: vi.fn(),
}));

const mockedUseAdminProduct = vi.mocked(useAdminProduct);
const mockedUseAdminProductUpdate = vi.mocked(useAdminProductUpdate);
const mockedUseProductFormReferenceData = vi.mocked(useProductFormReferenceData);
const mockedUseProductImageUpload = vi.mocked(useProductImageUpload);
const mockedUseProductImageAltTextUpdate = vi.mocked(useProductImageAltTextUpdate);
const mockedUseProductImageSetCover = vi.mocked(useProductImageSetCover);
const mockedUseProductImageReorder = vi.mocked(useProductImageReorder);
const mockedUseProductImageDelete = vi.mocked(useProductImageDelete);

const PRODUCT: RawAdminProductDetail = {
  id: "p1",
  type: "physical",
  category_id: "cat1",
  name: "Moon Lamp",
  slug: "moon-lamp",
  price: { amount_cents: 1800, currency: "USD" },
  description: null,
  seo_title: null,
  seo_description: null,
  og_image_url: null,
  is_visible: true,
  is_featured: false,
  is_available: true,
  material_id: null,
  colour_id: null,
  dimensions: null,
  weight_grams: null,
  production_lead_time_days: 2,
  batch_size: 2,
  max_quantity_per_line: 5,
  purchase_mode: "both",
  version: 3,
  average_rating: 0,
  review_count: 0,
  wishlist_count: 0,
  deleted_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  images: [
    { id: "i1", product_id: "p1", url: "/media/a.png", alt_text: "Front", sort_order: 0, is_cover: true, created_at: "x", updated_at: "x" },
  ],
};

function queryResult(overrides: Partial<ReturnType<typeof useAdminProduct>> = {}) {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn().mockResolvedValue({ data: PRODUCT }),
    ...overrides,
  } as unknown as ReturnType<typeof useAdminProduct>;
}

beforeEach(() => {
  mockedUseAdminProduct.mockReset();
  mockedUseAdminProductUpdate.mockReset();
  mockedUseProductFormReferenceData.mockReset();
  mockedUseProductImageUpload.mockReset();
  mockedUseProductImageAltTextUpdate.mockReset();
  mockedUseProductImageSetCover.mockReset();
  mockedUseProductImageReorder.mockReset();
  mockedUseProductImageDelete.mockReset();

  mockedUseAdminProductUpdate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
  mockedUseProductFormReferenceData.mockReturnValue({
    categories: [{ id: "cat1", name: "Toys" }],
    materials: [],
    colours: [],
    isLoading: false,
  });
  mockedUseProductImageUpload.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
  mockedUseProductImageAltTextUpdate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
  mockedUseProductImageSetCover.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
  mockedUseProductImageReorder.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
  mockedUseProductImageDelete.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
});

describe("AdminProductEditPage", () => {
  it("pre-fills the form from the fetched product and locks the product type", () => {
    mockedUseAdminProduct.mockReturnValue(queryResult({ data: PRODUCT }));
    render(<AdminProductEditPage />);

    expect(screen.getByLabelText("Name")).toHaveValue("Moon Lamp");
    expect(screen.getByLabelText("Slug")).toHaveValue("moon-lamp");
    const physicalRadio = screen.getByRole("radio", { name: "Physical" });
    expect(physicalRadio).toBeChecked();
    expect(physicalRadio).toBeDisabled();
    expect(screen.getByRole("radio", { name: /stl/i })).toBeDisabled();
  });

  it("saves with the fetched version in the body", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseAdminProductUpdate.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedUseAdminProduct.mockReturnValue(queryResult({ data: PRODUCT }));
    const user = userEvent.setup();
    render(<AdminProductEditPage />);

    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const body = mutateAsync.mock.calls[0]![0] as Record<string, unknown>;
    expect(body.version).toBe(3);
    expect(body).not.toHaveProperty("type");
  });

  it("on VERSION_CONFLICT, re-fetches and resets the form to the fresh state, showing a banner, without auto-retrying", async () => {
    const freshProduct = { ...PRODUCT, version: 4, name: "Moon Lamp (updated elsewhere)" };
    const mutateAsync = vi.fn().mockRejectedValue({ kind: "http", status: 409, code: "VERSION_CONFLICT", message: "x", raw: undefined });
    mockedUseAdminProductUpdate.mockReturnValue({ mutateAsync, isPending: false } as never);
    const refetch = vi.fn().mockResolvedValue({ data: freshProduct });
    mockedUseAdminProduct.mockReturnValue(queryResult({ data: PRODUCT, refetch }));
    const user = userEvent.setup();
    render(<AdminProductEditPage />);

    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/changed by someone else/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Name")).toHaveValue("Moon Lamp (updated elsewhere)"));
  });

  it("uploading an image calls the upload mutation via the injected driver", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseProductImageUpload.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedUseAdminProduct.mockReturnValue(queryResult({ data: PRODUCT }));
    const user = userEvent.setup();
    render(<AdminProductEditPage />);

    const file = new File(["x"], "photo.png", { type: "image/png" });
    const input = screen.getByLabelText(/add images/i) as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ file }));
  });

  it("saving edited alt text calls the alt-text mutation with the image id and new text", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseProductImageAltTextUpdate.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedUseAdminProduct.mockReturnValue(queryResult({ data: PRODUCT }));
    const user = userEvent.setup();
    render(<AdminProductEditPage />);

    const altTextInput = screen.getByLabelText("Alt text (image 1)");
    await user.clear(altTextInput);
    await user.type(altTextInput, "Updated alt text");
    await user.click(screen.getByRole("button", { name: /save alt text/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ imageId: "i1", altText: "Updated alt text" }));
  });

  it("setting a cover calls the cover mutation with the image id", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseProductImageSetCover.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedUseAdminProduct.mockReturnValue(
      queryResult({
        data: {
          ...PRODUCT,
          images: [
            { id: "i1", product_id: "p1", url: "/a.png", alt_text: "Front", sort_order: 0, is_cover: true, created_at: "x", updated_at: "x" },
            { id: "i2", product_id: "p1", url: "/b.png", alt_text: "Back", sort_order: 1, is_cover: false, created_at: "x", updated_at: "x" },
          ],
        },
      })
    );
    const user = userEvent.setup();
    render(<AdminProductEditPage />);

    await user.click(screen.getByRole("button", { name: /set as cover/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith("i2"));
  });

  it("deleting an image requires confirmation then calls the delete mutation", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseProductImageDelete.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedUseAdminProduct.mockReturnValue(queryResult({ data: PRODUCT }));
    const user = userEvent.setup();
    render(<AdminProductEditPage />);

    await user.click(screen.getByRole("button", { name: /delete/i }));
    await user.click(screen.getAllByRole("button", { name: "Delete" }).at(-1)!);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith("i1"));
  });
});
