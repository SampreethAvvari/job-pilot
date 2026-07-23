"use client";

import type { ReactNode } from "react";

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2">{children}</div>;
}

interface SegmentedOption {
  value: string;
  label: string;
}

interface SegmentedProps {
  value: string;
  onChange: (value: string) => void;
  options: SegmentedOption[];
}

export function Segmented({ value, onChange, options }: SegmentedProps) {
  return (
    <div className="card flex items-center gap-1 p-1">
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            className="btn btn-sm"
            style={active ? { background: "var(--blue-soft)", color: "var(--blue)" } : { color: "var(--ink-70)" }}
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
