"use client";

import { useEffect } from "react";

import type { Job } from "@/lib/types";
import { AssistantChat } from "@/components/assistant-chat";

/** Slide-over chat for one job. Mounted with key={job.id} so each job's
 * conversation is independent and ephemeral (nothing is persisted). */
export function AssistantDrawer({ job, onClose }: { job: Job; onClose: () => void }) {
  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end"
         style={{ background: "rgba(29, 29, 31, 0.32)" }}
         onClick={onClose}>
      <div className="card rise h-full w-full max-w-2xl overflow-y-auto p-4"
           style={{ borderRadius: 0, boxShadow: "var(--shadow-lg)" }}
           onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <div>
            <div className="eyebrow">assistant</div>
            <h2 className="display text-lg font-extrabold">{job.company}</h2>
          </div>
          <button onClick={onClose} className="btn-ghost px-2 py-1 text-xs">✕ close</button>
        </div>
        <AssistantChat lockedJob={job} />
      </div>
    </div>
  );
}
