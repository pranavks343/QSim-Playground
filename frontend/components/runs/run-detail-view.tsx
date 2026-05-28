"use client";

import Link from "next/link";
import { useMemo } from "react";

import { AgentCard } from "@/components/runs/agent-card";
import { BenchmarkPanel, type SimulationPreview } from "@/components/runs/benchmark-panel";
import { CircuitPanel, type CircuitPreview } from "@/components/runs/circuit-panel";
import { CriticVerdictPanel } from "@/components/runs/critic-verdict";
import { ExportBar } from "@/components/runs/export-bar";
import { FailureCard } from "@/components/runs/failure-card";
import { ProgressStepper } from "@/components/runs/progress-stepper";
import { RefinerPanel } from "@/components/runs/refiner-panel";
import { ScorecardTable } from "@/components/runs/scorecard-table";
import { useRunStream, type UseRunStreamResult } from "@/components/runs/use-run-stream";
import { StatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { deriveLiveState, AGENT_ORDER } from "@/lib/run-stream-state";
import type { PipelineEvent, Run } from "@/lib/types";

type Props = {
  initialRun: Run;
  initialEvents: PipelineEvent[];
};

export function RunDetailView({ initialRun, initialEvents }: Props) {
  const stream = useRunStream({
    runId: initialRun.id,
    initialRun,
    initialEvents
  });
  return <RunDetailContent stream={stream} />;
}

function RunDetailContent({ stream }: { stream: UseRunStreamResult }) {
  const { run, events, connection } = stream;
  const live = useMemo(() => deriveLiveState(events), [events]);

  const winnerAgent = live.criticVerdict?.winner_agent ?? run.winner_agent ?? null;
  const showFailure = live.terminal === "failed" || live.terminal === "cancelled";
  const failureKind = live.terminal === "cancelled" ? "cancelled" : "failed";

  const showScorecardTable =
    live.comparisonTable !== null || live.scorecards.length > 0 || run.scorecards != null;
  const showCritic = live.criticVerdict !== null || run.critic_verdict != null;
  const circuitPreview = run.circuit_data ?? circuitPreviewFromEvent(live.circuitEvent);
  const simulationPreview = run.sim_result ?? simulationPreviewFromEvent(live.simulationEvent);
  const showRefiner = live.refinerEvent !== null || run.refined_qubo != null;
  const showCircuit = circuitPreview !== null;
  const showBenchmark = simulationPreview !== null || run.classical_result != null;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link href="/dashboard" className="underline-offset-2 hover:underline">
              Dashboard
            </Link>
            <span>›</span>
            <span>Run {run.id.slice(0, 8)}</span>
          </div>
          <h1 className="mt-1 text-2xl font-semibold">
            {run.template ?? run.problem_ir.name}
          </h1>
          <p className="text-sm text-muted-foreground">
            {run.problem_ir.variables.length} variable
            {run.problem_ir.variables.length === 1 ? "" : "s"} ·{" "}
            {run.problem_ir.constraints?.length ?? 0} constraint
            {(run.problem_ir.constraints?.length ?? 0) === 1 ? "" : "s"} · created{" "}
            {new Date(run.created_at).toLocaleString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ConnectionBadge connection={connection} />
          <StatusBadge status={run.status} />
        </div>
      </header>

      <ProgressStepper stages={live.stages} />

      {showFailure ? (
        <FailureCard run={run} terminal={failureKind} reason={live.failureReason} />
      ) : null}

      <section aria-label="Agent formulations" className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">Agents</h2>
          <p className="text-xs text-muted-foreground">
            Five specialists race to formulate the QUBO. Cards animate as each finishes.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {AGENT_ORDER.map((name) => {
            const summary = live.agents[name];
            const qubo = run.qubos?.[name] ?? null;
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

      {showScorecardTable ? (
        <ScorecardTable
          scorecards={live.scorecards.length > 0 ? live.scorecards : Object.values(run.scorecards ?? {})}
          winnerAgent={winnerAgent}
          runnerUpAgent={
            live.criticVerdict?.runner_up_agent ??
            live.comparisonTable?.runner_up ??
            null
          }
        />
      ) : null}

      {showCritic ? (
        <CriticVerdictPanel verdict={live.criticVerdict ?? run.critic_verdict ?? null} />
      ) : null}

      {showRefiner ? (
        <RefinerPanel
          refined={run.refined_qubo ?? null}
          refinerEvent={live.refinerEvent}
        />
      ) : null}

      {showCircuit ? <CircuitPanel circuit={circuitPreview} /> : null}

      {showBenchmark ? (
        <BenchmarkPanel
          classical={run.classical_result ?? null}
          simulation={simulationPreview}
        />
      ) : null}

      <ExportBar run={run} />


      {!showScorecardTable && !showFailure ? (
        <Card className="border-dashed">
          <CardContent className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
            </span>
            Streaming live updates… cards will appear as the pipeline progresses.
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function circuitPreviewFromEvent(event: PipelineEvent | null): CircuitPreview | null {
  if (event === null) return null;
  const payload = event.payload;
  if (
    typeof payload.qubit_count !== "number" ||
    typeof payload.depth !== "number" ||
    typeof payload.gate_count !== "number"
  ) {
    return null;
  }
  return {
    qubit_count: payload.qubit_count,
    depth: payload.depth,
    gate_count: payload.gate_count
  };
}

function simulationPreviewFromEvent(event: PipelineEvent | null): SimulationPreview | null {
  if (event === null) return null;
  const payload = event.payload;
  if (
    typeof payload.best_bitstring !== "string" ||
    typeof payload.best_objective !== "number" ||
    typeof payload.quality_vs_classical !== "number"
  ) {
    return null;
  }
  return {
    best_bitstring: payload.best_bitstring,
    best_objective: payload.best_objective,
    quality_vs_classical: payload.quality_vs_classical
  };
}

function ConnectionBadge({ connection }: { connection: UseRunStreamResult["connection"] }) {
  const label =
    connection === "live"
      ? "Live"
      : connection === "polling"
        ? "Polling"
        : connection === "connecting"
          ? "Connecting…"
          : "Closed";
  const variant: "default" | "secondary" | "outline" =
    connection === "live" ? "default" : connection === "polling" ? "secondary" : "outline";
  return (
    <Badge variant={variant} className="font-mono text-[10px] uppercase tracking-wider">
      {label}
    </Badge>
  );
}
