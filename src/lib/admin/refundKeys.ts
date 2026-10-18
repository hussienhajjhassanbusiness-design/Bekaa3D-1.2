// #ARCHITECTURE-CANONICAL-REFUNDS-QUERY
//
// The ONE canonical query-key family for the refund server resource.
// A future refund-create/settle mutation MUST invalidate this family
// (and orderKeys where documented — FVS-032-IMPLEMENTATION-PLAN.md
// §3) rather than inventing a parallel key family for the same
// resource.
//
// `list()` takes no page/cursor argument — the real refund-list
// pagination shape is unconfirmed; a cursor/page argument can be
// added later without changing this file's exported shape.
export const refundKeys = {
  root: ["refunds"] as const,
  list: () => [...refundKeys.root, "list"] as const,
  detail: (refundId: string) => [...refundKeys.root, "detail", refundId] as const,
};
