import type { ReactNode } from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CustomRequestView } from "./CustomRequestView";
import AdminCustomRequestsPage from "@/app/admin/custom-requests/page";
import { apiClient } from "@/lib/api/apiClient";
import {
  customRequestsAdminApi,
  type CustomRequestDetailDTO,
  type CustomRequestFunnelDTO,
  type CustomRequestSummaryDTO,
} from "@/lib/admin/customRequests/customRequestsAdminApi";

const ID = "00000000-0000-4000-8000-000000000002";
const lead = (overrides: Partial<CustomRequestDetailDTO> = {}): CustomRequestDetailDTO => ({
  id: ID,
  name: "Rana",
  email: "rana@example.com",
  phone: "+961 70 123 456",
  project_title: "Cedar lamp",
  description: "<img src=x onerror=alert(1)>\nTall",
  preferred_material: "PLA",
  preferred_colour: null,
  dimensions: "20 cm",
  status: "contacted",
  quoted_amount_cents: null,
  currency: null,
  outcome: null,
  admin_notes: null,
  contacted_at: "2026-11-10T11:00:00Z",
  quoted_at: null,
  completed_at: null,
  closed_at: null,
  created_at: "2026-11-10T10:00:00Z",
  updated_at: "2026-11-10T11:00:00Z",
  attachments: [
    { id: "a-1", original_filename: "sketch <b>.png", mime_type: "image/png", size_bytes: 20480, expires_at: "2027-02-08T10:00:00Z", created_at: "2026-11-10T10:00:00Z" },
  ],
  ...overrides,
});
const FUNNEL: CustomRequestFunnelDTO = {
  from: "2026-08-12T00:00:00Z",
  to: "2026-11-11T00:00:00Z",
  submitted: 7,
  contacted: 5,
  quoted: 3,
  won: 1,
  lost: 1,
  open: 5,
  quoted_total_cents: 45000,
  won_total_cents: 12000,
  currency: "USD",
};

function renderWithQuery(node: ReactNode) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{node}</QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe("customRequestsAdminApi", () => {
  it("uses the exact routes, query names and CSRF on writes", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({});
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({});
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({});
    const blob = vi.spyOn(apiClient, "getBlob").mockResolvedValue({ blob: new Blob(), filename: null });
    await customRequestsAdminApi.listRequests({ status: "quoted", email: "a@b.co", cursor: "c" });
    await customRequestsAdminApi.getRequest(ID);
    await customRequestsAdminApi.getFunnel({ from: "2026-01-01T00:00:00.000Z" });
    await customRequestsAdminApi.getFunnel({});
    await customRequestsAdminApi.updateNotes(ID, null);
    await customRequestsAdminApi.transition(ID, { target_status: "quoted", quoted_amount_cents: 1500 });
    await customRequestsAdminApi.downloadAttachment(ID, "a-1");
    expect(get.mock.calls.map((c) => c[0])).toEqual([
      "/api/v1/admin/custom-requests?status=quoted&email=a%40b.co&cursor=c",
      `/api/v1/admin/custom-requests/${ID}`,
      "/api/v1/admin/analytics/custom-requests/funnel?from=2026-01-01T00%3A00%3A00.000Z",
      "/api/v1/admin/analytics/custom-requests/funnel",
    ]);
    expect(patch).toHaveBeenCalledWith(`/api/v1/admin/custom-requests/${ID}`, { admin_notes: null }, { csrf: true });
    expect(post).toHaveBeenCalledWith(`/api/v1/admin/custom-requests/${ID}/transition`, { target_status: "quoted", quoted_amount_cents: 1500 }, { csrf: true });
    expect(blob.mock.calls[0]![0]).toBe(`/api/v1/admin/custom-requests/${ID}/attachments/a-1/download`);
  });
});

describe("CustomRequestView", () => {
  it("renders visitor text as text and offers only the server's edges", async () => {
    vi.spyOn(customRequestsAdminApi, "getRequest").mockResolvedValue(lead());
    renderWithQuery(<CustomRequestView requestId={ID} />);
    expect(await screen.findByRole("heading", { name: "Cedar lamp" })).toBeInTheDocument();
    expect(screen.getByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
    expect(document.querySelector("main img, img")).toBeNull();
    expect(screen.getByText("sketch <b>.png")).toBeInTheDocument();
    const pipeline = screen.getByRole("region", { name: "Pipeline" });
    expect(within(pipeline).getAllByRole("button").map((b) => b.textContent)).toEqual(["Record quote", "Mark lost"]);
  });

  it("requires and sends a quote amount, then shows the server's result", async () => {
    const user = userEvent.setup();
    vi.spyOn(customRequestsAdminApi, "getRequest").mockResolvedValue(lead());
    const move = vi
      .spyOn(customRequestsAdminApi, "transition")
      .mockResolvedValue(lead({ status: "quoted", quoted_amount_cents: 15000, currency: "USD", quoted_at: "2026-11-11T09:00:00Z" }));
    renderWithQuery(<CustomRequestView requestId={ID} />);
    await user.click(await screen.findByRole("button", { name: "Record quote" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Record quote" }));
    expect(await within(dialog).findByText("Enter the quoted amount.")).toBeInTheDocument();
    expect(move).not.toHaveBeenCalled();
    await user.type(within(dialog).getByLabelText(/Quoted amount/), "150");
    await user.click(within(dialog).getByRole("button", { name: "Record quote" }));
    await waitFor(() => expect(move).toHaveBeenCalledWith(ID, { target_status: "quoted", quoted_amount_cents: 15000 }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByText("$150.00")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Pipeline" })).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Start work (won)",
      "Mark lost",
    ]);
  });

  it("sends no amount for other moves and shows safe 409 copy", async () => {
    const user = userEvent.setup();
    vi.spyOn(customRequestsAdminApi, "getRequest").mockResolvedValue(lead());
    const move = vi.spyOn(customRequestsAdminApi, "transition").mockRejectedValue({
      kind: "http",
      status: 409,
      code: "INVALID_STATE_TRANSITION",
      detail: "A lost request cannot become lost.",
      message: "x",
      raw: {},
    });
    renderWithQuery(<CustomRequestView requestId={ID} />);
    await user.click(await screen.findByRole("button", { name: "Mark lost" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark lost" }));
    expect(move).toHaveBeenCalledWith(ID, { target_status: "lost" });
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("already moved on");
    expect(screen.queryByText(/cannot become/)).not.toBeInTheDocument();
  });

  it("saves notes through PATCH (blank clears) and shows a confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(customRequestsAdminApi, "getRequest").mockResolvedValue(lead({ admin_notes: "Called once" }));
    const save = vi.spyOn(customRequestsAdminApi, "updateNotes").mockResolvedValue(lead({ admin_notes: null }));
    renderWithQuery(<CustomRequestView requestId={ID} />);
    const box = await screen.findByLabelText(/Internal note/);
    expect(box).toHaveValue("Called once");
    await user.clear(box);
    await user.click(within(screen.getByRole("region", { name: "Notes" })).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(ID, null));
    expect(await screen.findByText("Notes saved.")).toBeInTheDocument();
  });

  it("downloads an image through the admin session as a blob", async () => {
    const user = userEvent.setup();
    vi.spyOn(customRequestsAdminApi, "getRequest").mockResolvedValue(lead());
    const dl = vi.spyOn(customRequestsAdminApi, "downloadAttachment").mockResolvedValue({ blob: new Blob(["x"]), filename: "sketch _b_.png" });
    const createUrl = vi.fn(() => "blob:local");
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderWithQuery(<CustomRequestView requestId={ID} />);
    await user.click(await screen.findByRole("button", { name: "Download sketch <b>.png" }));
    await waitFor(() => expect(dl).toHaveBeenCalledWith(ID, "a-1"));
    expect(click).toHaveBeenCalled();
    expect(createUrl).toHaveBeenCalled();
  });

  it("explains an expired image", async () => {
    const user = userEvent.setup();
    vi.spyOn(customRequestsAdminApi, "getRequest").mockResolvedValue(lead());
    vi.spyOn(customRequestsAdminApi, "downloadAttachment").mockRejectedValue({ kind: "http", status: 404, code: "NOT_FOUND", message: "x", raw: {} });
    renderWithQuery(<CustomRequestView requestId={ID} />);
    await user.click(await screen.findByRole("button", { name: /Download/ }));
    expect(await screen.findByText("This image has expired or is no longer available.")).toBeInTheDocument();
  });

  it("offers nothing at a terminal status and renders 404 for unknown / malformed ids", async () => {
    vi.spyOn(customRequestsAdminApi, "getRequest").mockResolvedValueOnce(lead({ status: "lost", outcome: "lost", attachments: [] }));
    renderWithQuery(<CustomRequestView requestId={ID} />);
    expect(await screen.findByText("This request is finished. No further moves.")).toBeInTheDocument();
    expect(screen.getByText("Outcome: Lost")).toBeInTheDocument();
  });

  it("does not request a malformed id", () => {
    const get = vi.spyOn(customRequestsAdminApi, "getRequest");
    renderWithQuery(<CustomRequestView requestId="not-a-uuid" />);
    expect(screen.getByText(/page not found/i)).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });
});

describe("AdminCustomRequestsPage", () => {
  const summary = (overrides: Partial<CustomRequestSummaryDTO> = {}): CustomRequestSummaryDTO => ({
    id: ID,
    name: "Rana",
    email: "rana@example.com",
    phone: "+961 70 123 456",
    project_title: "Cedar lamp",
    status: "quoted",
    quoted_amount_cents: 15000,
    currency: "USD",
    outcome: null,
    attachment_count: 2,
    created_at: "2026-11-10T10:00:00Z",
    updated_at: "2026-11-10T10:00:00Z",
    ...overrides,
  });

  it("shows the server's funnel numbers and the pipeline list with backend filters", async () => {
    const user = userEvent.setup();
    const funnel = vi.spyOn(customRequestsAdminApi, "getFunnel").mockResolvedValue(FUNNEL);
    const list = vi.spyOn(customRequestsAdminApi, "listRequests").mockResolvedValue({ items: [summary()], next_cursor: null });
    renderWithQuery(<AdminCustomRequestsPage />);
    const region = await screen.findByRole("region", { name: "Funnel" });
    await within(region).findByText("$450.00");
    for (const [label, value] of [["Submitted", "7"], ["Contacted", "5"], ["Quoted", "3"], ["Won", "1"], ["Open", "5"], ["Won total", "$120.00"]] as [string, string][]) {
      expect(within(region).getByText(label).nextElementSibling).toHaveTextContent(value);
    }
    expect(funnel).toHaveBeenLastCalledWith({});
    expect(await screen.findByRole("link", { name: "Cedar lamp" })).toHaveAttribute("href", `/admin/custom-requests/${ID}`);
    expect(screen.getByText("$150.00")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Status"), "quoted");
    await waitFor(() => expect(list).toHaveBeenLastCalledWith({ status: "quoted" }));
  });

  it("explains a funnel range the server refuses", async () => {
    vi.spyOn(customRequestsAdminApi, "listRequests").mockResolvedValue({ items: [], next_cursor: null });
    vi.spyOn(customRequestsAdminApi, "getFunnel").mockRejectedValue({ kind: "http", status: 422, code: "VALIDATION_ERROR", message: "x", raw: {} });
    renderWithQuery(<AdminCustomRequestsPage />);
    expect(await screen.findByText(/at most 366 days/)).toBeInTheDocument();
  });
});
