import type { OrderDetailModel, OrderLineModel } from "./orderModel";

// #FVS031-ORDER-ACTION-AVAILABILITY (phase 5G)
//
// Which customer actions the order page OFFERS. A presentation hint only:
// every POST re-checks under the server's lock and its refusal is shown.
//
//   cancel           the server's own `can_cancel` flag, nothing else (the
//                    backend computes it with the same rule the POST
//                    enforces: a live physical line, cash or paid, every
//                    live physical line still `pending`). Never derived
//                    from product type here.
//   confirm receipt  the backend refuses (409 no_delivered_line) unless a
//                    PHYSICAL line is `delivered` or `picked_up` (an STL
//                    "delivered" is an emailed file, ADR-019). The detail
//                    has no capability flag for it, so the page offers it
//                    on exactly that rule, and only while one of those
//                    lines still lacks the server's `receipt_confirmed_at`
//                    (a repeat is a server no-op).
//   report problem   the same received-line rule; repeats are allowed (each
//                    is a new message to the team), so it stays offered.
const RECEIVED = new Set<string>(["delivered", "picked_up"]);

export const PROBLEM_MESSAGE_MAX = 5000;

export interface OrderActionAvailability {
  canCancel: boolean;
  canConfirmReceipt: boolean;
  canReportProblem: boolean;
  // The first server-recorded "I got it" / problem report, if any.
  receiptConfirmedAt: string | null;
  problemReportedAt: string | null;
}

function received(line: OrderLineModel): boolean {
  return line.productType === "physical" && RECEIVED.has(line.fulfillmentStatus);
}

function earliest(values: Array<string | null>): string | null {
  const present = values.filter((value): value is string => value !== null);
  if (present.length === 0) return null;
  return present.reduce((a, b) => (Date.parse(b) < Date.parse(a) ? b : a));
}

export function orderActionAvailability(order: OrderDetailModel): OrderActionAvailability {
  const receivedLines = order.lines.filter(received);
  const physical = order.lines.filter((line) => line.productType === "physical");
  return {
    canCancel: order.canCancel,
    canConfirmReceipt: receivedLines.some((line) => line.receiptConfirmedAt === null),
    canReportProblem: receivedLines.length > 0,
    receiptConfirmedAt: earliest(physical.map((line) => line.receiptConfirmedAt)),
    problemReportedAt: earliest(physical.map((line) => line.problemReportedAt)),
  };
}

// The server's ProblemReportCreate rules, mirrored for fast feedback only
// (the server's 422 is still handled): not blank after trimming, at most
// 5000 characters counted as Python does (code points, not UTF-16 units),
// no C0 control character or DEL other than tab, LF and CR.
const CONTROL_EXCEPT_LINE_BREAKS = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;

export const PROBLEM_MESSAGE_COPY = {
  blank: "Describe the problem before sending.",
  tooLong: `Keep your message to ${PROBLEM_MESSAGE_MAX} characters or fewer.`,
  control: "Remove the unsupported characters from your message.",
} as const;

export function problemMessageLength(message: string): number {
  return Array.from(message).length;
}

export function validateProblemMessage(message: string): string | null {
  if (message.trim() === "") return PROBLEM_MESSAGE_COPY.blank;
  if (problemMessageLength(message) > PROBLEM_MESSAGE_MAX) return PROBLEM_MESSAGE_COPY.tooLong;
  if (CONTROL_EXCEPT_LINE_BREAKS.test(message)) return PROBLEM_MESSAGE_COPY.control;
  return null;
}
