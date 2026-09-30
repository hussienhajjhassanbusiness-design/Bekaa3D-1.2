// FVS002-T07 — route skeleton only. Proves /register exists and renders
// through the root layout's shell (inherited automatically, same as every
// other route). The real registration form/mutation is contract-gated —
// see FVS-002-IMPLEMENTATION-PLAN.md §1, Task T08.
export default function Register() {
  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Create your account</h1>
      <p className="text-body text-text-secondary">Registration is coming soon.</p>
    </>
  );
}
