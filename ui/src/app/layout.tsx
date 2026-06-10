import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

import { Nav } from "@/components/nav";
import { RefreshButton } from "@/components/refresh-button";

const archivo = Archivo({
  subsets: ["latin"],
  variable: "--font-archivo",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-mono",
});

export const metadata: Metadata = {
  title: "JobPilot Console",
  description: "Mission control for the job hunt",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pilotName = process.env.PILOT_NAME ?? "Pilot";
  return (
    <html lang="en" className={`${archivo.variable} ${plexMono.variable}`}>
      <body>
        <div className="flex min-h-screen">
          <aside className="hidden w-56 shrink-0 flex-col border-r md:flex"
                 style={{ borderColor: "var(--line-soft)" }}>
            <div className="px-5 pt-6 pb-8">
              <div className="display text-lg font-extrabold tracking-tight">
                JOB<span style={{ color: "var(--amber)" }}>PILOT</span>
              </div>
              <div className="eyebrow mt-1">console v1</div>
            </div>
            <Nav />
            <div className="mt-auto px-5 pb-6">
              <div className="eyebrow">pilot</div>
              <div className="mt-1 text-xs" style={{ color: "var(--text-dim)" }}>
                {pilotName}
              </div>
            </div>
          </aside>

          <div className="min-w-0 flex-1">
            <header
              className="sticky top-0 z-50 flex items-center justify-between gap-4 border-b px-5 py-3 backdrop-blur"
              style={{ borderColor: "var(--line-soft)", background: "rgba(10,13,16,0.8)" }}
            >
              <div className="display text-sm font-bold tracking-tight md:hidden">
                JOB<span style={{ color: "var(--amber)" }}>PILOT</span>
              </div>
              <div className="eyebrow hidden md:block">
                every 6h · 00/06/12/18 ET · 7 sources
              </div>
              <RefreshButton />
            </header>
            <main className="px-5 py-6">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
