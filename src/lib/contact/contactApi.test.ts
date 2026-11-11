import { describe, it, expect, vi, beforeEach } from "vitest";
import { toContactPayload, submitContactMessage } from "./contactApi";

describe("toContactPayload", () => {
  it("trims values and omits blank optionals", () => {
    expect(
      toContactPayload({ name: "  Rana ", email: " r@example.com ", phone: "  ", subject: "", message: "\n Hello \n" }, "tok")
    ).toEqual({ name: "Rana", email: "r@example.com", message: "Hello", captcha_token: "tok" });
  });

  it("keeps the exact backend field names when optionals are present", () => {
    expect(
      toContactPayload({ name: "Rana", email: "r@example.com", phone: "+961 70 123 456", subject: "Hi", message: "Line 1\nLine 2" }, "tok")
    ).toEqual({ name: "Rana", email: "r@example.com", phone: "+961 70 123 456", subject: "Hi", message: "Line 1\nLine 2", captcha_token: "tok" });
  });
});

describe("submitContactMessage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("POSTs JSON to /api/v1/contact-messages without a CSRF header", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "m-1", created_at: "2026-11-11T10:00:00Z" }), { status: 201, headers: { "Content-Type": "application/json" } })
    );
    const receipt = await submitContactMessage({ name: "R", email: "r@example.com", message: "Hi", captcha_token: "tok" });
    expect(receipt).toEqual({ id: "m-1", created_at: "2026-11-11T10:00:00Z" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toMatch(/\/api\/v1\/contact-messages$/);
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBeNull();
    expect(JSON.parse(String(init?.body))).toEqual({ name: "R", email: "r@example.com", message: "Hi", captcha_token: "tok" });
  });
});
