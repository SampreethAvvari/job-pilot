"use client";

interface FitRingProps {
  fit: number | null;
  size?: number;
}

export default function FitRing({ fit, size = 44 }: FitRingProps) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const pct = fit === null ? 0 : Math.max(0, Math.min(100, fit));
  const tone =
    fit === null
      ? "var(--ink-10)"
      : fit >= 85
        ? "var(--emerald)"
        : fit >= 75
          ? "var(--blue)"
          : "var(--amber)";
  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      title={fit === null ? "not scored" : `fit ${fit}`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--ink-10)" strokeWidth={4} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={tone}
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * c} ${c}`}
        />
      </svg>
      <span
        className="absolute inset-0 grid place-items-center font-semibold"
        style={{ fontFamily: "var(--font-plex-mono)", fontSize: size * 0.3, color: tone }}
      >
        {fit === null ? "·" : fit}
      </span>
    </div>
  );
}
