"use client";

import Link from "next/link";

import { AgentCard } from "@/components/runs/agent-card";
import { BenchmarkPanel } from "@/components/runs/benchmark-panel";
import { CircuitPanel } from "@/components/runs/circuit-panel";
import { CriticVerdictPanel } from "@/components/runs/critic-verdict";
import { RefinerPanel } from "@/components/runs/refiner-panel";
import { ScorecardTable } from "@/components/runs/scorecard-table";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { AGENT_ORDER, type AgentSummary } from "@/lib/run-stream-state";
import type { SharedRun } from "@/lib/types";

type Props = {
  run: SharedRun;
};

export function SharedRunView({ run }: Props) {
  const winnerAgent = run.critic_verdict?.winner_agent ?? run.winner_agent ?? null;
  const scorecards = Object.values(run.scorecards ?? {});

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-8">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground">
            QSim Playground · Shared run
          </div>
          <h1 className="mt-1 text-2xl font-semibold">{run.template ?? run.problem_ir.name}</h1>
          <p className="text-sm text-muted-foreground">
            {run.problem_ir.variables.length} variable
            {run.problem_ir.variables.length === 1 ? "" : "s"} ·{" "}
            {run.problem_ir.constraints?.length ?? 0} constraint
            {(run.problem_ir.constraints?.length ?? 0) === 1 ? "" : "s"} · completed{" "}
            {run.completed_at ? new Date(run.completed_at).toLocaleString() : "—"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="uppercase tracking-wider">
            Read-only
          </Badge>
          <Link
            href="/"
            className="text-xs text-muted-foreground underline-offset-2 hover:underline"
          >
            About QSim →
          </Link>
        </div>
      </header>

      <section aria-label="Winning formulations">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {AGENT_ORDER.map((name) => {
            const qubo = run.qubos?.[name] ?? null;
            const summary: AgentSummary = {
              name,
              status: qubo ? "done" : "failed",
              estimatedQubits: qubo?.estimated_qubits ?? null,
              errorMessage: qubo ? null : "Agent output not retained on shared view."
            };
            return (
              <AgentCard
                key={name}
                agent={summary}
                qubo={qubo}
                isWinner={winnerAgent === name}
              />
            );
          })}
        </div>
      </section>

      {scorecards.length > 0 ? (
        <ScorecardTable
          scorecards={scorecards}
          winnerAgent={winnerAgent}
          runnerUpAgent={run.critic_verdict?.runner_up_agent ?? null}
        />
      ) : null}

      {run.critic_verdict ? <CriticVerdictPanel verdict={run.critic_verdict} /> : null}

      {run.refined_qubo ? (
        <RefinerPanel refined={run.refined_qubo} refinerEvent={null} />
      ) : null}

      {run.circuit_data ? <CircuitPanel circuit={run.circuit_data} /> : null}

      <BenchmarkPanel
        classical={run.classical_result ?? null}
        simulation={run.sim_result ?? null}
      />

      <Card className="border-dashed">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4 text-xs text-muted-foreground">
          <span>
            This page is a read-only snapshot. Personal identifiers and other runs are never
            included. Sharing can be disabled by the owner at any time.
          </span>
          <Link
            href="/"
            className="font-medium text-primary underline-offset-2 hover:underline"
          >
            Try QSim Playground →
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
