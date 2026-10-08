// #SECURITY-PAYMENT-RETURN-UNTRUSTED
//
// An identification helper ONLY. It reads exactly the one configured
// key and returns it — it never inspects, branches on, or is
// influenced by any other parameter (status-like or otherwise). A
// return URL may eventually identify WHICH order/payment to check;
// it must never decide its state. Deliberately NOT named
// `parsePaymentSuccessFromUrl`/`providerStatusFromQuery` or anything
// implying it extracts meaning beyond "which record to check"
// (FVS-027-IMPLEMENTATION-PLAN.md §0/T02).
export function extractReturnIdentifier(params: URLSearchParams, identifierKey: string): string | null {
  return params.get(identifierKey);
}
