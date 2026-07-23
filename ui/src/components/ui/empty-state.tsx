import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  hint?: string;
  action?: ReactNode;
}

export default function EmptyState({ title, hint, action }: EmptyStateProps) {
  return (
    <div className="card flex flex-col items-center gap-2 px-6 py-12 text-center">
      <div className="text-sm font-semibold" style={{ color: "var(--ink)" }}>
        {title}
      </div>
      {hint && (
        <div className="max-w-sm text-[13px]" style={{ color: "var(--ink-55)" }}>
          {hint}
        </div>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
