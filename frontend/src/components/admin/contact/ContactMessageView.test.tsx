import type { ReactNode } from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ContactMessageView } from "./ContactMessageView";
import AdminContactMessagesPage from "@/app/admin/contact-messages/page";
import { apiClient } from "@/lib/api/apiClient";
import { contactMessagesAdminApi, type ContactMessageDTO } from "@/lib/admin/contactMessages/contactMessagesAdminApi";

const ID = "00000000-0000-4000-8000-000000000001";
const message = (overrides: Partial<ContactMessageDTO> = {}): ContactMessageDTO => ({
  id: ID,
  name: "Rana",
  email: "rana@example.com",
  phone: null,
  subject: "Materials",
  message: "<img src=x onerror=alert(1)>\nSecond line",
  status: "new",
  created_at: "2026-11-10T10:00:00Z",
  updated_at: "2026-11-10T10:00:00Z",
  user_id: null,
  order_id: null,
  ...overrides,
});

function renderWithQuery(node: ReactNode) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{node}</QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe("contactMessagesAdminApi", () => {
  it("uses the exact backend routes, query names and CSRF on PATCH", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], next_cursor: null });
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({});
    await contactMessagesAdminApi.listMessages({ status: "new", created_after: "2026-11-01T00:00:00.000Z", email: "a@b.co", cursor: "c1" });
    await contactMessagesAdminApi.listMessages({});
    await contactMessagesAdminApi.getMessage(ID);
    await contactMessagesAdminApi.updateStatus(ID, "archived");
    expect(get.mock.calls).toEqual([
      ["/api/v1/admin/contact-messages?status=new&created_after=2026-11-01T00%3A00%3A00.000Z&email=a%40b.co&cursor=c1"],
      ["/api/v1/admin/contact-messages"],
      [`/api/v1/admin/contact-messages/${ID}`],
    ]);
    expect(patch).toHaveBeenCalledWith(`/api/v1/admin/contact-messages/${ID}`, { status: "archived" }, { csrf: true });
  });
});

describe("ContactMessageView", () => {
  it("renders visitor text as plain text and offers every forward status", async () => {
    vi.spyOn(contactMessagesAdminApi, "getMessage").mockResolvedValue(message());
    renderWithQuery(<ContactMessageView messageId={ID} />);
    expect(await screen.findByRole("heading", { name: "Materials" })).toBeInTheDocument();
    expect(screen.getByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByRole("link", { name: "rana@example.com" })).toHaveAttribute("href", "mailto:rana@example.com");
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Mark read", "Mark replied", "Archive"]);
  });

  it("confirms, PATCHes the chosen status and shows the server's result", async () => {
    const user = userEvent.setup();
    vi.spyOn(contactMessagesAdminApi, "getMessage").mockResolvedValue(message());
    const update = vi.spyOn(contactMessagesAdminApi, "updateStatus").mockResolvedValue(message({ status: "replied" }));
    renderWithQuery(<ContactMessageView messageId={ID} />);
    await user.click(await screen.findByRole("button", { name: "Mark replied" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Mark replied" }));
    await waitFor(() => expect(update).toHaveBeenCalledWith(ID, "replied"));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getAllByText("Replied").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Archive"]);
  });

  it("shows safe copy on a 409 and keeps the dialog open", async () => {
    const user = userEvent.setup();
    vi.spyOn(contactMessagesAdminApi, "getMessage").mockResolvedValue(message({ status: "read" }));
    vi.spyOn(contactMessagesAdminApi, "updateStatus").mockRejectedValue({
      kind: "http",
      status: 409,
      code: "INVALID_STATE_TRANSITION",
      detail: "A archived message cannot become replied.",
      message: "x",
      raw: {},
    });
    renderWithQuery(<ContactMessageView messageId={ID} />);
    await user.click(await screen.findByRole("button", { name: "Mark replied" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark replied" }));
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("already moved on");
    expect(screen.queryByText(/cannot become/)).not.toBeInTheDocument();
  });

  it("links an order problem report to its order and customer, with no actions once archived", async () => {
    vi.spyOn(contactMessagesAdminApi, "getMessage").mockResolvedValue(
      message({ status: "archived", order_id: "o-1", user_id: "u-1", subject: "Problem with order B3D-X" })
    );
    renderWithQuery(<ContactMessageView messageId={ID} />);
    expect(await screen.findByRole("link", { name: "View order" })).toHaveAttribute("href", "/admin/orders/o-1");
    expect(screen.getByRole("link", { name: "View customer" })).toHaveAttribute("href", "/admin/customers/u-1");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders not-found for a 404 and for a malformed id (without a request)", async () => {
    vi.spyOn(contactMessagesAdminApi, "getMessage").mockRejectedValue({ kind: "http", status: 404, code: "NOT_FOUND", message: "x", raw: {} });
    renderWithQuery(<ContactMessageView messageId={ID} />);
    expect(await screen.findByText(/page not found/i)).toBeInTheDocument();
  });

  it("does not request a malformed id", () => {
    const get = vi.spyOn(contactMessagesAdminApi, "getMessage");
    renderWithQuery(<ContactMessageView messageId="../etc" />);
    expect(screen.getByText(/page not found/i)).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });
});

describe("AdminContactMessagesPage", () => {
  it("lists the queue and sends exactly the chosen backend filters", async () => {
    const user = userEvent.setup();
    const list = vi
      .spyOn(contactMessagesAdminApi, "listMessages")
      .mockResolvedValue({ items: [message(), message({ id: "m-2", name: "Karim", subject: null, order_id: "o-1", status: "read" })], next_cursor: null });
    renderWithQuery(<AdminContactMessagesPage />);
    expect(await screen.findByRole("link", { name: "Rana" })).toHaveAttribute("href", `/admin/contact-messages/${ID}`);
    expect(screen.getByText("Order problem")).toBeInTheDocument();
    expect(list).toHaveBeenLastCalledWith({});
    await user.selectOptions(screen.getByLabelText("Status"), "read");
    await waitFor(() => expect(list).toHaveBeenLastCalledWith({ status: "read" }));
    await user.type(screen.getByLabelText("Sender email (exact)"), " rana@example.com ");
    await user.click(screen.getByRole("button", { name: "Filter" }));
    await waitFor(() => expect(list).toHaveBeenLastCalledWith({ status: "read", email: "rana@example.com" }));
  });
});
