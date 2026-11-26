import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminReferenceDataPage } from "./AdminReferenceDataPage";
import {
  useReferenceDataList,
  useReferenceDataCreate,
  useReferenceDataUpdate,
  useReferenceDataArchive,
} from "@/lib/admin/referenceData/useReferenceData";
import type { ReferenceDataEntry } from "./referenceDataTypes";

vi.mock("@/lib/admin/referenceData/useReferenceData", () => ({
  useReferenceDataList: vi.fn(),
  useReferenceDataCreate: vi.fn(),
  useReferenceDataUpdate: vi.fn(),
  useReferenceDataArchive: vi.fn(),
}));

const mockedList = vi.mocked(useReferenceDataList);
const mockedCreate = vi.mocked(useReferenceDataCreate);
const mockedUpdate = vi.mocked(useReferenceDataUpdate);
const mockedArchive = vi.mocked(useReferenceDataArchive);

const CONFIG = { entityLabelSingular: "Category", entityLabelPlural: "Categories", emptyStateMessage: "No categories yet." };

const LIVE_ENTRY: ReferenceDataEntry = { id: "c1", name: "Toys", isArchived: false, isActive: true };

function listResult(overrides: Partial<ReturnType<typeof useReferenceDataList>> = {}) {
  return { data: undefined, isLoading: false, isError: false, ...overrides } as ReturnType<typeof useReferenceDataList>;
}

beforeEach(() => {
  mockedList.mockReset();
  mockedCreate.mockReset();
  mockedUpdate.mockReset();
  mockedArchive.mockReset();
  mockedCreate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
  mockedUpdate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
  mockedArchive.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
});

describe("AdminReferenceDataPage", () => {
  it("shows an error banner when the list fails to load", () => {
    mockedList.mockReturnValue(listResult({ isError: true }));
    render(<AdminReferenceDataPage resource="categories" config={CONFIG} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("creating an entry calls the create mutation with the adapted input", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedCreate.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedList.mockReturnValue(listResult({ data: [] }));
    const user = userEvent.setup();
    render(<AdminReferenceDataPage resource="materials" config={CONFIG} />);

    await user.click(screen.getByRole("button", { name: /add category/i }));
    await user.type(screen.getByLabelText("Name"), "PLA");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ name: "PLA", slug: undefined }));
  });

  it("a SLUG_CONFLICT on save shows an inline field error, not a banner", async () => {
    const mutateAsync = vi.fn().mockRejectedValue({ kind: "http", status: 409, code: "SLUG_CONFLICT", message: "x", raw: undefined });
    mockedCreate.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedList.mockReturnValue(listResult({ data: [] }));
    const user = userEvent.setup();
    render(<AdminReferenceDataPage resource="materials" config={CONFIG} />);

    await user.click(screen.getByRole("button", { name: /add category/i }));
    await user.type(screen.getByLabelText("Name"), "PLA");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText("That name is already in use.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("archiving calls the archive mutation with the entry id, after confirming", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedArchive.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedList.mockReturnValue(listResult({ data: [LIVE_ENTRY] }));
    const user = userEvent.setup();
    render(<AdminReferenceDataPage resource="categories" config={CONFIG} />);

    await user.click(screen.getByRole("button", { name: /archive/i }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: /^archive$/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith("c1"));
  });

  it("a CATEGORY_IN_USE failure on archive shows a banner, not a field error", async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValue({ kind: "http", status: 409, code: "CATEGORY_IN_USE", message: "x", raw: undefined });
    mockedArchive.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedList.mockReturnValue(listResult({ data: [LIVE_ENTRY] }));
    const user = userEvent.setup();
    render(<AdminReferenceDataPage resource="categories" config={CONFIG} />);

    await user.click(screen.getByRole("button", { name: /archive/i }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^archive$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/live product/i);
  });

  it("toggling active calls update with only isActive", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUpdate.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedList.mockReturnValue(listResult({ data: [LIVE_ENTRY] }));
    const user = userEvent.setup();
    render(<AdminReferenceDataPage resource="categories" config={CONFIG} />);

    await user.click(screen.getByRole("button", { name: "Disable" }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ id: "c1", input: { isActive: false } }));
  });
});
