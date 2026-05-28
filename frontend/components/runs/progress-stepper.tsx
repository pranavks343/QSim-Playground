"use client";

import { Check, X } from "lucide-react";

import {
  STAGE_LABELS,
  STAGE_ORDER,
  type LiveRunState
} from "@/lib/run-stream-state";
import { cn } from "@/lib/utils";

type Props = {
  stages: LiveRunState["stages"];
};

export function ProgressStepper({ stages }: Props) {
  return (
    <ol className="flex w-full flex-wrap items-center gap-2 rounded-lg border bg-card p-3 text-sm">
      {STAGE_ORDER.map((stage, index) => {
        const status = stages[stage];
        return (
          <li key={stage} className="flex items-center gap-2">
            <span
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full border text-xs font-semibold",
                status === "done" &&
                  "border-success bg-success text-success-foreground",
                status === "active" &&
                  "border-primary bg-primary/10 text-primary animate-pulse",
                status === "failed" &&
                  "border-destructive bg-destructive text-destructive-foreground",
                status === "pending" && "border-border bg-card text-muted-foreground"
              )}
            >
              {status === "done" ? (
                <Check className="h-3 w-3" />
              ) : status === "failed" ? (
                <X className="h-3 w-3" />
              ) : (
                <span>{index + 1}</span>
              )}
            </span>
            <span
              className={cn(
                "text-xs font-medium",
                status === "pending" ? "text-muted-foreground" : "text-foreground"
              )}
            >
              {STAGE_LABELS[stage]}
            </span>
            {index < STAGE_ORDER.length - 1 ? (
              <span className="mx-1 h-px w-6 bg-border md:w-10" aria-hidden />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
