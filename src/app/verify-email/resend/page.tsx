// FVS002-T07 — route skeleton only. Proves /verify-email/resend exists and
// renders through the root layout's shell. The real resend mutation and
// cooldown are contract-gated — see FVS-002-IMPLEMENTATION-PLAN.md §1,
// Task T10.
export default function ResendVerification() {
  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Resend verification email</h1>
      <p className="text-body text-text-secondary">Resending verification emails is coming soon.</p>
    </>
  );
}
