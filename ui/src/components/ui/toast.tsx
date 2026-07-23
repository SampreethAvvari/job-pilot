"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

interface Toast {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  ttlMs?: number;
}

// Internal stack entry: the public Toast plus an id and its own ttl handle so
// each toast expires and dismisses independently. The public contract is
// unchanged, useToast() still returns (t: Toast) => void.
interface StackedToast extends Toast {
  id: number;
}

const MAX_TOASTS = 3;

const ToastCtx = createContext<(t: Toast) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<StackedToast[]>([]);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());
  const nextId = useRef(0);

  const clearTimer = useCallback((id: number) => {
    const handle = timers.current.get(id);
    if (handle) {
      clearTimeout(handle);
      timers.current.delete(id);
    }
  }, []);

  const dismiss = useCallback(
    (id: number) => {
      clearTimer(id);
      setToasts((list) => list.filter((t) => t.id !== id));
    },
    [clearTimer],
  );

  const show = useCallback(
    (t: Toast) => {
      const id = nextId.current++;
      setToasts((list) => {
        const next = [...list, { ...t, id }];
        // Cap the stack: pushing past MAX drops the oldest and clears its
        // timer, so an orphaned timer never fires against a removed toast.
        while (next.length > MAX_TOASTS) {
          const dropped = next.shift();
          if (dropped) clearTimer(dropped.id);
        }
        return next;
      });
      timers.current.set(
        id,
        setTimeout(() => dismiss(id), t.ttlMs ?? 6000),
      );
    },
    [clearTimer, dismiss],
  );

  // Clear every outstanding timer when the provider unmounts.
  useEffect(() => {
    const map = timers.current;
    return () => {
      for (const handle of map.values()) clearTimeout(handle);
      map.clear();
    };
  }, []);

  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toasts.length > 0 && (
        <div className="fixed bottom-20 left-1/2 z-50 flex -translate-x-1/2 flex-col gap-2 md:bottom-6">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className="card rise flex items-center gap-3 px-4 py-3"
              style={{ boxShadow: "var(--shadow-lg)" }}
            >
              <span className="text-[13px]">{toast.message}</span>
              {toast.actionLabel && (
                <button
                  className="btn btn-sm btn-ghost font-semibold"
                  style={{ color: "var(--blue)" }}
                  onClick={() => {
                    toast.onAction?.();
                    dismiss(toast.id);
                  }}
                >
                  {toast.actionLabel}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </ToastCtx.Provider>
  );
}
