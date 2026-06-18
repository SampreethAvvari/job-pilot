"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { isApplied } from "@/lib/status-sets";
import type { Job } from "@/lib/types";

const LINKS = [
  { href: "/", label: "Dashboard", glyph: "◈" },
  { href: "/jobs", label: "Jobs", glyph: "≣" },
  { href: "/applied", label: "Applied", glyph: "✓" },
  { href: "/resumes", label: "Resumes", glyph: "❑" },
  { href: "/replies", label: "Replies", glyph: "⮌" },
  { href: "/companies", label: "Companies", glyph: "▦" },
  { href: "/outreach", label: "Outreach", glyph: "✉" },
  { href: "/assistant", label: "Assistant", glyph: "✦" },
];

export function Nav() {
  const path = usePathname();
  const [appliedCount, setAppliedCount] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/jobs")
      .then((r) => r.json())
      .then((d) => {
        if (d.jobs) {
          setAppliedCount((d.jobs as Job[]).filter((j) => isApplied(j.status)).length);
        }
      })
      .catch(() => {});
  }, [path]);

  return (
    <nav className="flex flex-col gap-1 px-3">
      {LINKS.map((l) => (
        <Link key={l.href} href={l.href}
              className={`navlink ${path === l.href ? "active" : ""}`}>
          <span aria-hidden>{l.glyph}</span>
          {l.label}
          {l.href === "/applied" && appliedCount !== null && (
            <span className="ml-auto text-[11px]" style={{ color: "var(--green)" }}>
              ({appliedCount})
            </span>
          )}
        </Link>
      ))}
    </nav>
  );
}
