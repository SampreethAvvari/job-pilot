"use client";

import { useEffect, type MouseEventHandler, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  width?: number;
  children: ReactNode;
}

export default function Modal({ open, onClose, width = 480, children }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Client-only portal target; SSR pass (and the closed state) render nothing.
  if (!open || typeof document === "undefined") return null;

  const onOverlayClick: MouseEventHandler<HTMLDivElement> = (e) => {
    if (e.target === e.currentTarget) onClose();
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(29, 29, 31, 0.32)" }}
      onMouseDown={onOverlayClick}
    >
      <div
        className="card rise max-h-[90vh] overflow-y-auto p-6"
        style={{ width: `min(${width}px, 94vw)`, boxShadow: "var(--shadow-lg)" }}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
