import { describe, it, expect } from "vitest";
import { adaptNotification } from "./notificationAdapter";
import type { NotificationReadDTO, NotificationType } from "./notificationTypes";

// Phase 2 auth/account batch — "Specific event comes from payload.event.
// Unknown event must render safely with a generic fallback. Do not crash
// on an unknown payload event." The backend confirms the payload.event
// registry is currently EMPTY (BACKEND-RESPONSE.md P2-5) — every real
// notification today is, by definition, an "unknown event" from this
// adapter's point of view, so the generic-fallback path is the only path
// that matters in production right now.

function dto(overrides: Partial<NotificationReadDTO> = {}): NotificationReadDTO {
  return {
    id: "n1",
    type: "account",
    payload: {},
    read: false,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("adaptNotification", () => {
  it("maps id and read straight through", () => {
    const result = adaptNotification(dto({ id: "n2", read: true }));
    expect(result.id).toBe("n2");
    expect(result.isRead).toBe(true);
  });

  it("maps type straight through", () => {
    expect(adaptNotification(dto({ type: "order" })).type).toBe("order");
  });

  it("never crashes on an empty payload, producing a safe generic title/body", () => {
    const result = adaptNotification(dto({ type: "payment", payload: {} }));
    expect(result.title.length).toBeGreaterThan(0);
    expect(result.body.length).toBeGreaterThan(0);
  });

  it("never crashes when payload.event is present but of an unrecognized type (number, object, array)", () => {
    expect(() => adaptNotification(dto({ payload: { event: 42 } }))).not.toThrow();
    expect(() => adaptNotification(dto({ payload: { event: { nested: true } } }))).not.toThrow();
    expect(() => adaptNotification(dto({ payload: { event: ["a", "b"] } }))).not.toThrow();
  });

  it("never crashes when payload itself is missing expected shape (extra/weird keys)", () => {
    expect(() => adaptNotification(dto({ payload: { unexpected: "shape", nested: { a: 1 } } }))).not.toThrow();
  });

  it("produces distinct, non-empty titles for each of the seven current notification types", () => {
    const types: NotificationType[] = ["account", "order", "payment", "refund", "offer", "download", "custom_request"];
    const titles = types.map((type) => adaptNotification(dto({ type })).title);

    for (const title of titles) {
      expect(title.length).toBeGreaterThan(0);
    }
    expect(new Set(titles).size).toBe(types.length);
  });

  it("falls back to a generic, non-empty title for an unrecognized type string, never a crash", () => {
    const result = adaptNotification(dto({ type: "some_future_type_not_yet_in_the_enum" }));
    expect(result.title.length).toBeGreaterThan(0);
  });

  it("never renders payload content unescaped/as HTML — body stays a plain string", () => {
    const result = adaptNotification(dto({ payload: { event: "<script>alert(1)</script>" } }));
    expect(typeof result.body).toBe("string");
  });

  it("labels the current custom_request type (ADR-030) with its own title, not the generic fallback", () => {
    const result = adaptNotification(dto({ type: "custom_request" }));
    expect(result.title).toBe("Custom request");
    expect(result.body).toBe("You have a new custom request notification.");
    expect(result.type).toBe("custom_request");
  });

  it("uses the generic 'Notification' title for an unknown future type, keeping the type string intact", () => {
    const result = adaptNotification(dto({ type: "brand_new_type", payload: { event: "something_new" } }));
    expect(result.title).toBe("Notification");
    expect(result.type).toBe("brand_new_type");
    expect(result.body.length).toBeGreaterThan(0);
  });

  it("never crashes on an unknown future event under a known type", () => {
    const result = adaptNotification(dto({ type: "custom_request", payload: { event: "future_event_x" } }));
    expect(result.title).toBe("Custom request");
    expect(result.body.length).toBeGreaterThan(0);
  });

  it("passes the real created_at through as createdAt (Batch 5 row timestamp)", () => {
    expect(adaptNotification(dto({ created_at: "2026-11-09T08:15:00Z" })).createdAt).toBe("2026-11-09T08:15:00Z");
  });
});
