"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, createIrRun, createTemplateRun } from "@/lib/api";
import type { Run } from "@/lib/types";

type Props = {
  run: Run;
  terminal: "failed" | "cancelled";
  reason: string | null;
};

export function FailureCard({ run, terminal, reason }: Props) {
  const router = useRouter();
  const [retrying, setRetrying] = useState(false);
  const [feedback, setFeedback] = useState<"positive" | "negative" | null>(null);

  const title = terminal === "cancelled" ? "Run cancelled" : "Run failed";

  const handleRetry = async () => {
    setRetrying(true);
    try {
      let runId: string | null = null;
      if (run.input_source === "template" && run.template) {
        runId = (await createTemplateRun(run.template)).run_id;
      } else if (run.input_source === "code") {
        // We do not have the original source code in the run record;
        // hand the user back to the new-run page with the IR pre-filled.
        router.push("/new");
        return;
      } else {
        runId = (await createIrRun(run.problem_ir)).run_id;
      }
      router.push(`/runs/${runId}`);
    } catch (err) {
      const message = err instanceof ApiError ? `${err.message} (${err.status})` : "Could not retry";
      toast.error(message);
    } finally {
      setRetrying(false);
    }
  };

  return (
    <Card className="border-destructive/40 bg-destructive/5">
      <CardHeader>
        <CardTitle className="text-destructive">{title}</CardTitle>
        <CardDescription>
          {terminal === "cancelled"
            ? "This run was cancelled before it could finish."
            : "The pipeline did not finish successfully. Here is what we know:"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="rounded-md border bg-card p-3 text-sm text-foreground">
          {reason ?? run.error ?? "No additional detail was reported."}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={handleRetry} disabled={retrying}>
            {retrying ? "Retrying…" : "Retry with same input"}
          </Button>
          <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
            <span>How clear was this error?</span>
            <button
              type="button"
              onClick={() => {
                setFeedback("positive");
                toast.success("Thanks for the signal!");
              }}
              className={
                "rounded-md border px-2 py-1 transition-colors " +
                (feedback === "positive"
                  ? "border-success text-success"
                  : "border-border hover:border-foreground")
              }
              aria-label="The error message was clear"
            >
              👍
            </button>
            <button
              type="button"
              onClick={() => {
                setFeedback("negative");
                toast("Logged — we'll work on a clearer message.");
              }}
              className={
                "rounded-md border px-2 py-1 transition-colors " +
                (feedback === "negative"
                  ? "border-destructive text-destructive"
                  : "border-border hover:border-foreground")
              }
              aria-label="The error message needs work"
            >
              👎
            </button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
