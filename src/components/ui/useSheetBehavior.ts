"use client";

import { useEffect } from "react";

export interface SheetBehaviorOptions {
  open: boolean;
  onClose: () => void;
  // The sheet only exists below this breakpoint; growing past it closes
  // the sheet (e.g. "(min-width: 1024px)").
  closeAtQuery: string;
}

// #SHARED-SHEET-BEHAVIOR (redesign Batch 3)
//
// The two side sheets built on DialogShell — the header's mobile menu and
// the shop's filter drawer — share the behaviour DialogShell does not own:
// the page behind a modal sheet does not scroll, and the sheet closes
// itself when the viewport grows past the breakpoint where its trigger
// disappears (rotation, resize). Focus trap, Escape, backdrop and focus
// return stay with DialogShell.
export function useSheetBehavior({ open, onClose, closeAtQuery }: SheetBehaviorOptions): void {
  useEffect(() => {
    if (!open) return;

    const root = document.documentElement;
    const previousOverflow = root.style.overflow;
    root.style.overflow = "hidden";

    const media = window.matchMedia(closeAtQuery);
    const handleChange = (event: MediaQueryListEvent) => {
      if (event.matches) onClose();
    };
    media.addEventListener("change", handleChange);

    return () => {
      root.style.overflow = previousOverflow;
      media.removeEventListener("change", handleChange);
    };
  }, [open, onClose, closeAtQuery]);
}
