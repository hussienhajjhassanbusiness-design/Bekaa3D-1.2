import { buildLoginRedirectPath } from "@/lib/auth/returnTo";

export interface LoggedOutCartPromptProps {
  returnToPath?: string;
}

// #FVS025-LOGGED-OUT-CART-PROMPT
//
// Resolves FVS-025-IMPLEMENTATION-PLAN.md §0's recorded source
// discrepancy: /cart (the route) stays wrapped in the real,
// unmodified ProtectedRoute, which redirects an anonymous visitor
// before any inline content could render. This prompt instead belongs
// to MiniCartDrawer — not behind ProtectedRoute, since the header
// renders on every public page regardless of auth state. Reuses
// buildLoginRedirectPath (FVS-003) directly — no duplicated
// redirect-safety logic. No guest-cart affordance of any kind.
export function LoggedOutCartPrompt({ returnToPath = "/cart" }: LoggedOutCartPromptProps) {
  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center">
      <p className="text-body text-text-secondary">Log in to see your cart.</p>
      <a href={buildLoginRedirectPath(returnToPath)} className="rounded-md bg-brand-dark-green px-4 py-2 text-text-on-brand">
        Log in
      </a>
    </div>
  );
}
