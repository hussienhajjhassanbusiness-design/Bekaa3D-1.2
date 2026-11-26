import { useState } from "react";

export interface UseCursorPagination {
  cursor: string | undefined;
  hasPrevious: boolean;
  goNext: (nextCursor: string) => void;
  goPrevious: () => void;
  reset: () => void;
}

interface PaginationState {
  resetKey: unknown;
  stack: (string | undefined)[];
}

const INITIAL_STACK: (string | undefined)[] = [undefined];

// Phase 3 — every admin list is cursor-paginated (C2: {items,
// next_cursor}, never a page number or total count). This hook keeps a
// client-side stack of visited cursors so AdminTable's controlled
// hasPrevious/hasNext/onPrevious/onNext props have something to bind to
// — there is no backend "go back" cursor, so a client stack is the only
// way "Previous" can exist at all. `resetKey` lets a caller (e.g. a
// search box) drop back to page one whenever it changes.
//
// The previous resetKey is tracked inside the state object itself
// (React's documented "adjust state while rendering" pattern), not a
// ref — react-hooks/refs forbids reading/writing a ref during render,
// but comparing-then-conditionally-setState is explicitly fine and
// gives the same "reset is visible on the very render that changed the
// key" result without an extra effect tick.
export function useCursorPagination(resetKey?: unknown): UseCursorPagination {
  const [state, setState] = useState<PaginationState>({ resetKey, stack: INITIAL_STACK });

  if (state.resetKey !== resetKey) {
    setState({ resetKey, stack: INITIAL_STACK });
  }

  const stack = state.resetKey === resetKey ? state.stack : INITIAL_STACK;

  return {
    cursor: stack[stack.length - 1],
    hasPrevious: stack.length > 1,
    goNext(nextCursor: string) {
      setState((current) => ({ ...current, stack: [...current.stack, nextCursor] }));
    },
    goPrevious() {
      setState((current) => ({
        ...current,
        stack: current.stack.length > 1 ? current.stack.slice(0, -1) : current.stack,
      }));
    },
    reset() {
      setState((current) => ({ ...current, stack: INITIAL_STACK }));
    },
  };
}
