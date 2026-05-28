import type { Run } from "@/lib/types";

export type ExportControlsState = {
  /** Whether export and share controls should be visible at all. */
  visible: boolean;
  /** Whether the share toggle should reflect "shared" state. */
  shared: boolean;
  /** Whether the share toggle's destructive (un-share) variant should show. */
  canUnshare: boolean;
};

export function deriveExportControlsState(run: Pick<Run, "status" | "shared">): ExportControlsState {
  const visible = run.status === "done";
  const shared = run.shared === true;
  return {
    visible,
    shared,
    canUnshare: shared
  };
}

export function shareUrlFor(runId: string, origin: string | null = null): string {
  const base = origin ?? (typeof window !== "undefined" ? window.location.origin : "");
  return `${base}/share/${runId}`;
}
