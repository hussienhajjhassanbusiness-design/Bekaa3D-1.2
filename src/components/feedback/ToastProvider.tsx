"use client";

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { Toast, type ToastVariant } from "./Toast";

export interface ShowToastInput {
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  showToast: (input: ShowToastInput) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}

interface ActiveToast extends ShowToastInput {
  id: number;
}

// FVS001-T12: simple array state + a provider-local incrementing counter for
// ids — deliberately no queue/eviction/priority policy, no external store.
// A real ordering/stacking policy is deferred until a slice has enough
// simultaneous events to need one (FRONTEND-VERTICAL-SLICE-PLAN.md §17).
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ActiveToast[]>([]);
  const nextId = useRef(0);

  const showToast = useCallback((input: ShowToastInput) => {
    const id = nextId.current++;
    setToasts((current) => [...current, { ...input, id }]);
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4">
        {toasts.map((toast) => (
          <Toast
            key={toast.id}
            message={toast.message}
            variant={toast.variant}
            onDismiss={() => dismiss(toast.id)}
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
}
