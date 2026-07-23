"use client";

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

interface Toast {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  ttlMs?: number;
}

const ToastCtx = createContext<(t: Toast) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const show = useCallback((t: Toast) => {
    if (timer.current) clearTimeout(timer.current);
    setToast(t);
    timer.current = setTimeout(() => setToast(null), t.ttlMs ?? 6000);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && (
        <div
          className="card rise fixed bottom-20 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 px-4 py-3 md:bottom-6"
          style={{ boxShadow: "var(--shadow-lg)" }}
        >
          <span className="text-[13px]">{toast.message}</span>
          {toast.actionLabel && (
            <button
              className="btn btn-sm btn-ghost font-semibold"
              style={{ color: "var(--blue)" }}
              onClick={() => {
                toast.onAction?.();
                setToast(null);
              }}
            >
              {toast.actionLabel}
            </button>
          )}
        </div>
      )}
    </ToastCtx.Provider>
  );
}
