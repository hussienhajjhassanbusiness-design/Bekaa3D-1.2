"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

export interface NotificationBellProps {
  unreadCount: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children?: ReactNode;
}

const FOCUSABLE_SELECTOR = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

// #FVS008-NOTIFICATION-CENTER
//
// Pure presentation — no data fetch, no polling, no mutation. Standalone
// this batch (FVS-008-IMPLEMENTATION-PLAN.md §2's own scope note): not
// yet mounted into Header, since that would mean showing a permanently
// fabricated unread count in production before the real data source
// (T05/T06) exists.
//
// aria-label is always exactly "Notifications, N unread", including for
// zero — FRONTEND-VERTICAL-SLICE-PLAN.md's own specified format,
// verbatim, never silently reinterpreted. No large-count formatting
// (e.g. "99+") is invented — that is explicitly product-owned behavior.
//
// Reuses the same accessible primitives ConfirmDialog (FVS-007) already
// proved out (a Tab focus trap, Escape-closes, outside-click-closes) as
// its own implementation, rather than a shared component — a
// notification panel is not a confirm/cancel dialog, and this batch's
// own instruction is explicit not to misuse ConfirmDialog for this.
export function NotificationBell({ unreadCount, open, onOpenChange, children }: NotificationBellProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onOpenChange(false);
        return;
      }

      if (event.key === "Tab") {
        const panel = panelRef.current;
        if (!panel) {
          return;
        }
        const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
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

    function handlePointerDown(event: MouseEvent) {
      const panel = panelRef.current;
      const trigger = triggerRef.current;
      const target = event.target as Node;
      if (panel?.contains(target) || trigger?.contains(target)) {
        return;
      }
      onOpenChange(false);
    }

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [open, onOpenChange]);

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-label={`Notifications, ${unreadCount} unread`}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => onOpenChange(!open)}
        className="relative rounded-full p-2 text-on-surface"
      >
        <BellIcon />
        {unreadCount > 0 && (
          <span
            aria-hidden="true"
            className="absolute right-0 top-0 rounded-full bg-error px-1 text-xs text-on-error"
          >
            {unreadCount}
          </span>
        )}
      </button>
      {open && (
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-label="Notifications"
          className="fixed inset-0 z-50 overflow-y-auto bg-surface-container-lowest p-4 tablet:absolute tablet:inset-auto tablet:right-0 tablet:top-full tablet:mt-2 tablet:w-96 tablet:rounded-card tablet:border tablet:border-outline-variant tablet:shadow-2xl"
        >
          {children}
        </div>
      )}
    </div>
  );
}

function BellIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="h-6 w-6">
      <path
        d="M12 2a6 6 0 0 0-6 6v3.17c0 .53-.21 1.04-.59 1.41L4 14h16l-1.41-1.41a2 2 0 0 1-.59-1.42V8a6 6 0 0 0-6-6ZM10 18a2 2 0 1 0 4 0"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
