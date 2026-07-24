"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Home" },
  { href: "/jobs", label: "Jobs" },
  { href: "/applied", label: "Applied" },
  { href: "/companies", label: "Companies" },
  { href: "/replies", label: "Replies" },
  { href: "/outreach", label: "Outreach" },
  { href: "/assistant", label: "Assistant" },
  { href: "/knowledge", label: "Knowledge" },
];

export default function MobileNav() {
  const path = usePathname();
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 flex gap-1 overflow-x-auto border-t px-2 py-2 md:hidden"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      {TABS.map((t) => {
        const active = t.href === "/" ? path === "/" : path.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`navlink whitespace-nowrap ${active ? "active" : ""}`}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
