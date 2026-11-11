import { describe, it, expect } from "vitest";
import { adaptOrderDetail } from "./orderModel";
import { detailDTO, lineDTO, stlLineDTO } from "./orderFixtures";
import { orderActionAvailability, PROBLEM_MESSAGE_MAX, validateProblemMessage } from "./orderActions";

const order = (...args: Parameters<typeof detailDTO>) => adaptOrderDetail(detailDTO(...args));

describe("orderActionAvailability", () => {
  it("offers cancel only while the server's can_cancel is true", () => {
    expect(orderActionAvailability(order({ can_cancel: true })).canCancel).toBe(true);
    expect(orderActionAvailability(order({ can_cancel: false })).canCancel).toBe(false);
  });

  it("never offers cancel on an STL-only order the server refuses", () => {
    const stlOnly = order({ can_cancel: false, fulfillment_method: null, lines: [stlLineDTO()] });
    expect(orderActionAvailability(stlOnly).canCancel).toBe(false);
  });

  it("offers neither receipt action before any physical line is delivered or picked up", () => {
    const a = orderActionAvailability(order({ lines: [lineDTO({ fulfillment_status: "shipped" })] }));
    expect(a.canConfirmReceipt).toBe(false);
    expect(a.canReportProblem).toBe(false);
  });

  it("ignores an STL line marked delivered: emailing a file is not receiving it", () => {
    const a = orderActionAvailability(order({ lines: [stlLineDTO({ fulfillment_status: "delivered" })] }));
    expect(a.canConfirmReceipt).toBe(false);
    expect(a.canReportProblem).toBe(false);
  });

  it("offers both on a delivered or picked-up physical line", () => {
    for (const status of ["delivered", "picked_up"] as const) {
      const a = orderActionAvailability(order({ lines: [lineDTO({ fulfillment_status: status })] }));
      expect(a.canConfirmReceipt).toBe(true);
      expect(a.canReportProblem).toBe(true);
    }
  });

  it("stops offering confirm once every received line carries receipt_confirmed_at; report stays", () => {
    const a = orderActionAvailability(
      order({
        lines: [
          lineDTO({ fulfillment_status: "delivered", receipt_confirmed_at: "2026-11-12T10:00:00Z" }),
          lineDTO({ id: "l2", fulfillment_status: "shipped" }),
        ],
      })
    );
    expect(a.canConfirmReceipt).toBe(false);
    expect(a.canReportProblem).toBe(true);
    expect(a.receiptConfirmedAt).toBe("2026-11-12T10:00:00Z");
  });

  it("offers confirm again when a newly delivered line is not yet confirmed", () => {
    const a = orderActionAvailability(
      order({
        lines: [
          lineDTO({ fulfillment_status: "delivered", receipt_confirmed_at: "2026-11-12T10:00:00Z" }),
          lineDTO({ id: "l2", fulfillment_status: "delivered" }),
        ],
      })
    );
    expect(a.canConfirmReceipt).toBe(true);
  });

  it("reports the earliest server timestamps for the recorded receipt and problem states", () => {
    const a = orderActionAvailability(
      order({
        lines: [
          lineDTO({ fulfillment_status: "delivered", problem_reported_at: "2026-11-13T10:00:00Z" }),
          lineDTO({ id: "l2", fulfillment_status: "delivered", problem_reported_at: "2026-11-12T10:00:00Z" }),
        ],
      })
    );
    expect(a.problemReportedAt).toBe("2026-11-12T10:00:00Z");
    expect(a.receiptConfirmedAt).toBeNull();
  });
});

describe("validateProblemMessage", () => {
  it("accepts ordinary text with line breaks and tabs", () => {
    expect(validateProblemMessage("The lid\r\nis\tcracked")).toBeNull();
  });

  it("refuses a blank message", () => {
    expect(validateProblemMessage("")).toBe("Describe the problem before sending.");
    expect(validateProblemMessage("  \n\t ")).toBe("Describe the problem before sending.");
  });

  it("counts characters the way the server does (code points), up to 5000", () => {
    expect(PROBLEM_MESSAGE_MAX).toBe(5000);
    expect(validateProblemMessage("a".repeat(5000))).toBeNull();
    expect(validateProblemMessage("a".repeat(5001))).toBe("Keep your message to 5000 characters or fewer.");
    // 5000 emoji = 10000 UTF-16 units, but 5000 characters to the server.
    expect(validateProblemMessage("\u{1F600}".repeat(5000))).toBeNull();
  });

  it("refuses control characters other than tab, line feed and carriage return", () => {
    expect(validateProblemMessage("bad\u0000text")).toBe("Remove the unsupported characters from your message.");
    expect(validateProblemMessage("bad\u007ftext")).toBe("Remove the unsupported characters from your message.");
  });
});
