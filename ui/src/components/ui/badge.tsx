import type { ReactNode } from "react";

type Tone = "blue" | "emerald" | "violet" | "amber" | "rose" | "neutral";

interface BadgeProps {
  tone: Tone;
  children: ReactNode;
}

const TONE_STYLE: Record<Tone, { background: string; color: string }> = {
  blue: { background: "var(--blue-soft)", color: "var(--blue)" },
  emerald: { background: "var(--emerald-soft)", color: "var(--emerald)" },
  violet: { background: "var(--violet-soft)", color: "var(--violet)" },
  amber: { background: "var(--amber-soft)", color: "var(--amber)" },
  rose: { background: "var(--rose-soft)", color: "var(--rose)" },
  neutral: { background: "var(--surface-2)", color: "var(--ink-55)" },
};

export default function Badge({ tone, children }: BadgeProps) {
  return (
    <span className="pill" style={TONE_STYLE[tone]}>
      {children}
    </span>
  );
}
