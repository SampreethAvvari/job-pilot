interface SkeletonProps {
  className?: string;
}

export default function Skeleton({ className }: SkeletonProps) {
  const classes = ["animate-pulse", "rounded-md", className].filter(Boolean).join(" ");
  return <div className={classes} style={{ background: "var(--surface-2)" }} />;
}
