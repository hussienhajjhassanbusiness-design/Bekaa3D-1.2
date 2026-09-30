// FVS002-T07 — route skeleton only. Proves /verify-email exists and renders
// through the root layout's shell. The real verification mutation/token
// handling is contract-gated — see FVS-002-IMPLEMENTATION-PLAN.md §1,
// Task T09.
export default function VerifyEmail() {
  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Verify your email</h1>
      <p className="text-body text-text-secondary">Email verification is coming soon.</p>
    </>
  );
}
