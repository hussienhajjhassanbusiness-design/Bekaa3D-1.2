// Content for AppLayout's <header> landmark — not a second <header> element.
// Text/token-based brand treatment only; the real logo asset placement is a
// deferred content decision, not this skeleton's job. No nav items exist in
// FVS-001, so there is nothing interactive here yet.
export function Header() {
  return (
    <div className="border-b border-border-default px-4 py-3 tablet:px-6 desktop:px-8">
      <span className="text-h3 font-semibold text-text-primary">Bekaa3D</span>
    </div>
  );
}
