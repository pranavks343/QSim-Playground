"use client";

import { useState } from "react";

import { QuboMatrixDialog } from "@/components/runs/qubo-matrix-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { AgentName, AgentSummary } from "@/lib/run-stream-state";
import type { QUBOOutput } from "@/lib/types";
import { cn } from "@/lib/utils";

const AGENT_LABELS: Record<AgentName, string> = {
  penalty: "Penalty",
  slack: "Slack",
  graph: "Graph",
  decomp: "Decomp",
  domain: "Domain"
};

const AGENT_SUBTITLES: Record<AgentName, string> = {
  penalty: "Linear constraint penalties",
  slack: "Slack-variable encoding",
  graph: "Graph-theoretic structure",
  decomp: "Problem decomposition",
  domain: "Domain-aware tailoring"
};

type Props = {
  agent: AgentSummary;
  qubo: QUBOOutput | null;
  isWinner: boolean;
};

export function AgentCard({ agent, qubo, isWinner }: Props) {
  const [matrixOpen, setMatrixOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const stateClasses = cardStateClasses(agent.status, isWinner);

  return (
    <>
      <Card
        data-agent={agent.name}
        data-status={agent.status}
        className={cn("flex h-full flex-col transition-colors", stateClasses)}
      >
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-2">
            <div>
              <CardTitle className="text-base capitalize">{AGENT_LABELS[agent.name]}</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">{AGENT_SUBTITLES[agent.name]}</p>
            </div>
            <StatusBadge status={agent.status} isWinner={isWinner} />
          </div>
        </CardHeader>
        <CardContent className="flex flex-1 flex-col gap-3 pb-4 pt-0">
          {agent.status === "pending" ? (
            <p className="text-sm text-muted-foreground">Waiting…</p>
          ) : null}

          {agent.status === "running" ? (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">Formulating…</p>
              <Progress value={undefined} className="animate-pulse" />
            </div>
          ) : null}

          {agent.status === "failed" ? (
            <div className="space-y-1">
              <p className="text-sm font-medium text-destructive">Agent failed</p>
              <p className="text-xs text-muted-foreground">
                {agent.errorMessage ?? "Unknown error"}
              </p>
              <p className="text-[11px] text-muted-foreground">
                The pipeline continues as long as at least three agents succeed.
              </p>
            </div>
          ) : null}

          {agent.status === "done" ? (
            <div className="flex flex-1 flex-col gap-3">
              <div className="flex items-center gap-2 text-sm">
                <Badge variant="secondary" className="font-mono">
                  {agent.estimatedQubits ?? qubo?.estimated_qubits ?? "—"} qubits
                </Badge>
                {qubo ? (
                  <span className="text-xs text-muted-foreground">
                    {Object.keys(qubo.parameters_used ?? {}).length} parameter
                    {Object.keys(qubo.parameters_used ?? {}).length === 1 ? "" : "s"}
                  </span>
                ) : null}
              </div>
              {qubo ? (
                <p className="line-clamp-2 text-sm text-muted-foreground">{qubo.strategy}</p>
              ) : (
                <p className="text-xs text-muted-foreground">Strategy details arrive when the run completes.</p>
              )}
              {qubo ? (
                <div className="space-y-2">
                  <p
                    className={cn(
                      "text-xs text-muted-foreground",
                      expanded ? "whitespace-pre-line" : "line-clamp-3"
                    )}
                  >
                    {qubo.justification}
                  </p>
                  <button
                    type="button"
                    onClick={() => setExpanded((value) => !value)}
                    className="text-xs font-medium text-primary underline-offset-2 hover:underline"
                  >
                    {expanded ? "Show less" : "Read full reasoning"}
                  </button>
                </div>
              ) : null}
              <div className="mt-auto">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={qubo === null}
                  onClick={() => setMatrixOpen(true)}
                >
                  View QUBO
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
      <QuboMatrixDialog open={matrixOpen} onOpenChange={setMatrixOpen} qubo={qubo} />
    </>
  );
}

function cardStateClasses(status: AgentSummary["status"], isWinner: boolean): string {
  if (status === "failed") {
    return "border-destructive/60";
  }
  if (status === "running") {
    return "border-primary/60 shadow-sm";
  }
  if (status === "done") {
    return isWinner
      ? "border-success/70 bg-success/5"
      : "border-border";
  }
  return "border-dashed text-muted-foreground";
}

function StatusBadge({
  status,
  isWinner
}: {
  status: AgentSummary["status"];
  isWinner: boolean;
}) {
  if (isWinner && status === "done") {
    return <Badge className="bg-success text-success-foreground">Winner</Badge>;
  }
  switch (status) {
    case "pending":
      return <Badge variant="outline">Pending</Badge>;
    case "running":
      return <Badge className="animate-pulse bg-primary text-primary-foreground">Running</Badge>;
    case "done":
      return <Badge variant="secondary">Done</Badge>;
    case "failed":
      return <Badge className="bg-destructive text-destructive-foreground">Failed</Badge>;
    default:
      return null;
  }
}
