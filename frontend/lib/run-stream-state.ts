import type {
  ComparisonTable,
  CriticVerdict,
  PipelineEvent,
  Run,
  Scorecard
} from "@/lib/types";

export const AGENT_ORDER = ["penalty", "slack", "graph", "decomp", "domain"] as const;
export type AgentName = (typeof AGENT_ORDER)[number];

export type AgentStatus = "pending" | "running" | "done" | "failed";

export type AgentSummary = {
  name: AgentName;
  status: AgentStatus;
  estimatedQubits: number | null;
  errorMessage: string | null;
};

export const STAGE_ORDER = [
  "agents",
  "evaluate",
  "critic",
  "refine",
  "circuit",
  "simulate",
  "done"
] as const;
export type Stage = (typeof STAGE_ORDER)[number];

export const STAGE_LABELS: Record<Stage, string> = {
  agents: "Agents",
  evaluate: "Evaluate",
  critic: "Critic",
  refine: "Refine",
  circuit: "Circuit",
  simulate: "Simulate",
  done: "Done"
};

export type StageStatus = "pending" | "active" | "done" | "failed";

export type LiveRunState = {
  agents: Record<AgentName, AgentSummary>;
  stages: Record<Stage, StageStatus>;
  scorecards: Scorecard[];
  comparisonTable: ComparisonTable | null;
  criticVerdict: CriticVerdict | null;
  refinerEvent: PipelineEvent | null;
  circuitEvent: PipelineEvent | null;
  simulationEvent: PipelineEvent | null;
  terminal: "done" | "failed" | "cancelled" | null;
  failureReason: string | null;
};

export function emptyLiveState(): LiveRunState {
  const agents: Record<AgentName, AgentSummary> = {} as Record<AgentName, AgentSummary>;
  for (const name of AGENT_ORDER) {
    agents[name] = {
      name,
      status: "pending",
      estimatedQubits: null,
      errorMessage: null
    };
  }
  const stages: Record<Stage, StageStatus> = {} as Record<Stage, StageStatus>;
  for (const stage of STAGE_ORDER) {
    stages[stage] = "pending";
  }
  return {
    agents,
    stages,
    scorecards: [],
    comparisonTable: null,
    criticVerdict: null,
    refinerEvent: null,
    circuitEvent: null,
    simulationEvent: null,
    terminal: null,
    failureReason: null
  };
}

function isAgentName(value: unknown): value is AgentName {
  return typeof value === "string" && (AGENT_ORDER as readonly string[]).includes(value);
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asScorecard(value: unknown): Scorecard | null {
  if (value === null || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (typeof v.agent_name !== "string") return null;
  if (typeof v.qubit_count !== "number") return null;
  return v as unknown as Scorecard;
}

function asComparisonTable(value: unknown): ComparisonTable | null {
  if (value === null || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (!Array.isArray(v.scorecards) || typeof v.top_agent !== "string") return null;
  return v as unknown as ComparisonTable;
}

function asCriticVerdict(value: unknown): CriticVerdict | null {
  if (value === null || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (typeof v.winner_agent !== "string" || typeof v.rationale !== "string") return null;
  return v as unknown as CriticVerdict;
}

export function deriveLiveState(events: PipelineEvent[]): LiveRunState {
  const state = emptyLiveState();
  const scorecardByAgent = new Map<string, Scorecard>();

  // Once any agent starts, the agent stage is active.
  let anyAgentStarted = false;
  let allAgentsDone = false;

  for (const event of events) {
    const payload = event.payload ?? {};
    switch (event.event_type) {
      case "agent_started": {
        const agentName = (payload as { agent_name?: unknown }).agent_name;
        if (isAgentName(agentName)) {
          state.agents[agentName] = {
            name: agentName,
            status: "running",
            estimatedQubits: null,
            errorMessage: null
          };
          anyAgentStarted = true;
        }
        break;
      }
      case "agent_done": {
        const agentName = (payload as { agent_name?: unknown }).agent_name;
        const estimatedQubits = asNumber((payload as { estimated_qubits?: unknown }).estimated_qubits);
        if (isAgentName(agentName)) {
          state.agents[agentName] = {
            name: agentName,
            status: "done",
            estimatedQubits,
            errorMessage: null
          };
        }
        break;
      }
      case "agent_failed": {
        const agentName = (payload as { agent_name?: unknown }).agent_name;
        const errorMessage = asString((payload as { error?: unknown }).error);
        if (isAgentName(agentName)) {
          state.agents[agentName] = {
            name: agentName,
            status: "failed",
            estimatedQubits: null,
            errorMessage
          };
        }
        break;
      }
      case "scorecard_ready": {
        const sc = asScorecard(payload);
        if (sc !== null) {
          scorecardByAgent.set(sc.agent_name, sc);
        }
        break;
      }
      case "comparison_ready": {
        const table = asComparisonTable(payload);
        if (table !== null) state.comparisonTable = table;
        break;
      }
      case "critic_verdict": {
        const verdict = asCriticVerdict(payload);
        if (verdict !== null) state.criticVerdict = verdict;
        break;
      }
      case "refiner_done":
        state.refinerEvent = event;
        break;
      case "circuit_ready":
        state.circuitEvent = event;
        break;
      case "simulation_done":
        state.simulationEvent = event;
        break;
      case "pipeline_done":
        state.terminal = "done";
        break;
      case "pipeline_cancelled":
        state.terminal = "cancelled";
        state.failureReason =
          asString((payload as { reason?: unknown }).reason) ?? "Run was cancelled.";
        break;
      case "pipeline_failed":
        state.terminal = "failed";
        state.failureReason =
          asString((payload as { message?: unknown }).message) ??
          asString((payload as { reason?: unknown }).reason) ??
          "Pipeline failed.";
        break;
      default:
        break;
    }
  }

  state.scorecards = AGENT_ORDER.map((name) => scorecardByAgent.get(name)).filter(
    (sc): sc is Scorecard => sc !== undefined
  );

  allAgentsDone = AGENT_ORDER.every((name) => {
    const s = state.agents[name].status;
    return s === "done" || s === "failed";
  });

  // Stage transitions.
  if (anyAgentStarted) state.stages.agents = "active";
  if (allAgentsDone) state.stages.agents = "done";
  if (state.scorecards.length > 0 || state.comparisonTable !== null) {
    state.stages.evaluate = "active";
  }
  if (state.comparisonTable !== null) state.stages.evaluate = "done";
  if (state.comparisonTable !== null) state.stages.critic = "active";
  if (state.criticVerdict !== null) state.stages.critic = "done";
  if (state.criticVerdict !== null) state.stages.refine = "active";
  if (state.refinerEvent !== null) state.stages.refine = "done";
  if (state.refinerEvent !== null) state.stages.circuit = "active";
  if (state.circuitEvent !== null) state.stages.circuit = "done";
  if (state.circuitEvent !== null) state.stages.simulate = "active";
  if (state.simulationEvent !== null) state.stages.simulate = "done";
  if (state.terminal === "done") state.stages.done = "done";
  if (state.terminal === "failed" || state.terminal === "cancelled") {
    // Mark the in-flight stage as failed so the stepper shows where it stopped.
    for (const stage of STAGE_ORDER) {
      if (state.stages[stage] === "active") {
        state.stages[stage] = "failed";
        break;
      }
    }
  }

  return state;
}

export function isTerminalEvent(event: PipelineEvent): boolean {
  return (
    event.event_type === "pipeline_done" ||
    event.event_type === "pipeline_failed" ||
    event.event_type === "pipeline_cancelled"
  );
}

export function mergeRunSnapshot(run: Run, live: LiveRunState): LiveRunState {
  // Once the run has terminal state, prefer the persisted fields.
  if (live.terminal !== null) return live;
  if (run.status === "done" || run.status === "failed" || run.status === "cancelled" || run.status === "timeout") {
    return {
      ...live,
      terminal: run.status === "done" ? "done" : run.status === "cancelled" ? "cancelled" : "failed",
      failureReason: run.error ?? live.failureReason
    };
  }
  return live;
}
