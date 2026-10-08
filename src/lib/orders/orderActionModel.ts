// #ARCHITECTURE-SERVER-PROVIDED-ORDER-ACTIONS
//
// The neutral, domain-free server-provided-affordance shape. Extracted
// here (FVS-031-IMPLEMENTATION-PLAN.md §1) so both FVS-030's admin
// transitions and this slice's customer cancellation consume the same
// primitive — the frontend renders exactly the actions it is given,
// never deriving legality from a locally-guessed status. `id`/`label`
// are never claimed backend field names.
export interface OrderActionAffordance {
  id: string;
  label: string;
  requiresConfirmation: boolean;
}
