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
  { href: "/knowledge", label: "Knowledge", glyph: "⬡" },
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
          <span aria-hidden className="font-mono text-[13px] leading-none">{l.glyph}</span>
          {l.label}
          {l.href === "/applied" && appliedCount !== null && (
            <span
              className="ml-auto rounded-full px-1.5 py-0.5 text-[11px] font-semibold leading-none"
              style={{ background: "var(--blue-soft)", color: "var(--blue)" }}
            >
              {appliedCount}
            </span>
          )}
        </Link>
      ))}
    </nav>
  );
}
