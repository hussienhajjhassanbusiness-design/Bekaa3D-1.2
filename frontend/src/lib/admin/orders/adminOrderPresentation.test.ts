import { describe, it, expect } from "vitest";
import {
  ADMIN_ORDER_MESSAGES,
  canRecordCashHandover,
  describeAdminLineStatus,
  describeAdminOrderError,
  describeAdminRefundStatus,
  describeCancelReason,
  describeTransitionAction,
  orderCancelOffer,
} from "./adminOrderPresentation";
import { adminDetailDTO, adminLineDTO } from "./adminOrderFixtures";

const http = (status: number, code: string, extra: Record<string, unknown> = {}) => ({
  kind: "http" as const,
  status,
  code,
  message: "RAW",
  detail: "RAW DETAIL",
  raw: { status, code, detail: "RAW DETAIL", ...extra },
});

describe("labels", () => {
  it("shows the real line states, STL as manual email delivery, unknown values safely", () => {
    expect(describeAdminLineStatus("in_production", "physical").label).toBe("In production");
    expect(describeAdminLineStatus("pending", "physical").label).toBe("Pending");
    expect(describeAdminLineStatus("awaiting_delivery", "stl").label).toBe("Awaiting email delivery");
    expect(describeAdminLineStatus("delivered", "stl").label).toBe("Sent by email");
    expect(describeAdminLineStatus("delivered", "physical").label).toBe("Delivered");
    expect(describeAdminLineStatus("teleported", "physical").label).toBe("Status unavailable");
    expect(describeAdminLineStatus("toString", "physical").label).toBe("Status unavailable");
  });

  it("names each server-provided target, never echoing an unknown one", () => {
    expect(describeTransitionAction("in_production", "physical")).toBe("Start production");
    expect(describeTransitionAction("delivered", "stl")).toBe("Mark STL emailed");
    expect(describeTransitionAction("cancelled", "physical")).toBe("Cancel line");
    expect(describeTransitionAction("zzz", "physical")).toBe("Update line");
    expect(describeCancelReason("no_show")).toBe("Customer didn't collect");
    expect(describeAdminRefundStatus("settled").label).toBe("Settled");
    expect(describeAdminRefundStatus("weird").label).toBe("Status unavailable");
  });
});

describe("canRecordCashHandover", () => {
  it("only for an unpaid cash order whose every live line is at the ready state", () => {
    const shipped = adminLineDTO({ fulfillment_status: "shipped", available_actions: [] });
    expect(canRecordCashHandover(adminDetailDTO({ lines: [shipped] }))).toBe(true);
    expect(canRecordCashHandover(adminDetailDTO({ lines: [shipped, adminLineDTO({ id: "x", fulfillment_status: "cancelled" })] }))).toBe(true);
    expect(canRecordCashHandover(adminDetailDTO({ lines: [shipped, adminLineDTO({ id: "y", fulfillment_status: "ready_to_ship" })] }))).toBe(false);
    expect(canRecordCashHandover(adminDetailDTO({ fulfillment_method: "pickup", lines: [adminLineDTO({ fulfillment_status: "ready_for_pickup" })] }))).toBe(true);
    expect(canRecordCashHandover(adminDetailDTO({ payment_due: false, lines: [shipped] }))).toBe(false);
    expect(canRecordCashHandover(adminDetailDTO({ payment_method: "online", lines: [shipped] }))).toBe(false);
    expect(canRecordCashHandover(adminDetailDTO({ lines: [adminLineDTO({ fulfillment_status: "cancelled" })] }))).toBe(false);
  });
});

describe("orderCancelOffer", () => {
  it("offers the order cancel from lines the server itself lets be cancelled, before shipping", () => {
    const offer = orderCancelOffer(adminDetailDTO());
    expect(offer?.lines).toHaveLength(1);
    expect(offer?.reasonRequired).toBe(false);
  });

  it("requires a reason when a ready line takes one, offering the server's reasons", () => {
    const offer = orderCancelOffer(
      adminDetailDTO({
        lines: [
          adminLineDTO({
            fulfillment_status: "ready_to_ship",
            available_actions: [{ target_status: "cancelled", cancel_reasons: ["refused", "other"] }],
          }),
        ],
      })
    );
    expect(offer).toEqual(expect.objectContaining({ reasons: ["refused", "other"], reasonRequired: true }));
  });

  it("no offer for shipped, STL or lines the server doesn't offer cancel for", () => {
    expect(
      orderCancelOffer(
        adminDetailDTO({
          lines: [
            adminLineDTO({ fulfillment_status: "shipped", available_actions: [{ target_status: "cancelled", cancel_reasons: ["other"] }] }),
            adminLineDTO({ id: "s", product_type: "stl", fulfillment_status: "awaiting_delivery", available_actions: [{ target_status: "delivered", cancel_reasons: [] }] }),
            adminLineDTO({ id: "p", fulfillment_status: "pending", available_actions: [] }),
          ],
        })
      )
    ).toBeNull();
  });
});

describe("describeAdminOrderError", () => {
  it("maps every documented 409 reason to frontend copy and asks for a re-read", () => {
    for (const reason of ["payment_required", "cash_handover_required", "not_a_legal_edge", "line_closed", "lines_not_ready", "already_recorded", "already_delivered"]) {
      const o = describeAdminOrderError(http(409, "INVALID_STATE_TRANSITION", { reason }));
      expect(o.refetchOrder).toBe(true);
      expect(o.message).not.toMatch(/RAW/);
      expect(o.message).not.toBe(ADMIN_ORDER_MESSAGES.stateChanged);
    }
    expect(describeAdminOrderError(http(409, "INVALID_STATE_TRANSITION", { reason: "new_one" })).message).toBe(
      ADMIN_ORDER_MESSAGES.stateChanged
    );
  });

  it("CASH_AMOUNT_MISMATCH names the server's amount_due", () => {
    expect(describeAdminOrderError(http(422, "CASH_AMOUNT_MISMATCH", { amount_due: { amount_cents: 3600, currency: "USD" } })).message).toBe(
      "The cash entered must be exactly the amount due ($36.00)."
    );
    expect(describeAdminOrderError(http(422, "CASH_AMOUNT_MISMATCH", { amount_due: "x" })).message).toBe(
      "The cash entered must be exactly the amount due."
    );
  });

  it("CSRF, MFA, session, not found, rate limit, network", () => {
    expect(describeAdminOrderError(http(403, "CSRF_INVALID")).message).toBe(ADMIN_ORDER_MESSAGES.csrf);
    expect(describeAdminOrderError({ kind: "csrf", message: "x", raw: null }).message).toBe(ADMIN_ORDER_MESSAGES.csrf);
    expect(describeAdminOrderError(http(401, "MFA_REQUIRED")).message).toBe(ADMIN_ORDER_MESSAGES.mfa);
    expect(describeAdminOrderError(http(401, "AUTH_REQUIRED")).message).toBe(ADMIN_ORDER_MESSAGES.session);
    expect(describeAdminOrderError(http(404, "NOT_FOUND"))).toEqual({ message: ADMIN_ORDER_MESSAGES.notFound, refetchOrder: true });
    expect(describeAdminOrderError(http(429, "RATE_LIMITED")).message).toBe(ADMIN_ORDER_MESSAGES.rateLimited);
    expect(describeAdminOrderError({ kind: "network", message: "x", raw: null })).toEqual({ message: ADMIN_ORDER_MESSAGES.network, refetchOrder: true });
    expect(describeAdminOrderError(http(409, "ORDER_TOTAL_MISMATCH")).message).toBe(ADMIN_ORDER_MESSAGES.totalMismatch);
  });
});
