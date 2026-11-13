"use client";

import { useEffect, useLayoutEffect, useRef, type MouseEvent, type ReactNode } from "react";

export interface DialogShellProps {
  open: boolean;
  onClose: () => void;
  // Suppresses Escape/backdrop-click while true (e.g. a pending
  // mutation) — mirrors the exact invariant ConfirmDialog already had
  // (`isConfirming`), generalized to any busy state.
  isBusy?: boolean;
  labelledBy: string;
  describedBy?: string;
  children: ReactNode;
  // Replaces the panel's default class list entirely when supplied —
  // never merged — so a caller (e.g. FVS-025's MiniCartDrawer) can
  // position the panel as an edge-anchored drawer/bottom-sheet
  // (typically via its own `fixed` positioning, escaping the
  // backdrop's centering layout) without a second focus-trap
  // implementation. Omitting it keeps the exact existing centered-
  // modal classes, unchanged for every current caller.
  panelClassName?: string;
}

// Stitch modal card (COMPONENT-SPECS §48, COMPONENT-MIGRATION "DialogShell"):
// white card, 12px radius, soft outline-variant border, shadow-2xl, 24px
// padding (32px from tablet). Width and the 90vh scroll cap are unchanged
// (e2e asserts the dialog never exceeds the viewport).
const DEFAULT_PANEL_CLASSNAME =
  "w-full max-w-md max-h-[90vh] overflow-y-auto rounded-card border border-outline-variant/30 bg-surface-container-lowest p-6 shadow-2xl tablet:p-8";

// Scrim: on-surface at 40% with a light blur (Stitch drawer/modal overlay).
const BACKDROP_CLASSNAME = "fixed inset-0 z-50 flex items-center justify-center bg-on-surface/40 p-4 backdrop-blur-sm";

const FOCUSABLE_SELECTOR = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

// #SHARED-DIALOG-SHELL
//
// Extracted from FVS-007's own ConfirmDialog (which had its own
// independent focus-trap/Escape/backdrop implementation) so neither it
// nor any future dialog elsewhere in the app needs a second,
// separately-maintained copy of the same accessible-dialog mechanics.
// Carries NO business/domain knowledge — title, description,
// and actions are entirely the caller's `children`; this shell owns
// only role/aria-modal, the labelledby/describedby wiring, the Tab
// focus trap, Escape handling, backdrop-click handling, and focus
// restoration to the triggering element on close.
//
// Built as a manually-managed accessible dialog rather than native
// <dialog>.showModal() — this project's jsdom version does not
// implement showModal/close, which would make this component
// untestable at the unit level despite working in a real browser (the
// same reasoning ConfirmDialog's own original implementation recorded).
export function DialogShell({
  open,
  onClose,
  isBusy = false,
  labelledBy,
  describedBy,
  children,
  panelClassName,
}: DialogShellProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<Element | null>(null);

  // A layout effect, not a passive one: every layout effect runs before
  // any passive effect, so the trigger is recorded before a child that
  // focuses its first field in its own mount effect (AddressForm, Phase
  // 5B) moves focus into the dialog. A passive effect here ran after the
  // child's and recorded the child's input as the "trigger", so focus was
  // never returned on close.
  useLayoutEffect(() => {
    if (open) {
      triggerRef.current = document.activeElement;
    } else if (triggerRef.current instanceof HTMLElement) {
      triggerRef.current.focus();
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (!isBusy) {
          onClose();
        }
        return;
      }

      if (event.key === "Tab") {
        const dialog = dialogRef.current;
        if (!dialog) {
          return;
        }
        const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!first || !last) {
          return;
        }
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, isBusy, onClose]);

  if (!open) {
    return null;
  }

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isBusy) {
      onClose();
    }
  }

  return (
    <div className={BACKDROP_CLASSNAME} onClick={handleBackdropClick}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        className={panelClassName ?? DEFAULT_PANEL_CLASSNAME}
      >
        {children}
      </div>
    </div>
  );
}
