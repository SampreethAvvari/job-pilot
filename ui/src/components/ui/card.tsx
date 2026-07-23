"use client";

import type { MouseEventHandler, ReactNode } from "react";

interface CardProps {
  className?: string;
  children: ReactNode;
  onClick?: MouseEventHandler<HTMLDivElement>;
}

export default function Card({ className, children, onClick }: CardProps) {
  const classes = ["card", onClick ? "card-hover cursor-pointer" : "", className]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={classes} onClick={onClick}>
      {children}
    </div>
  );
}
