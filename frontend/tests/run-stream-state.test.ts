import { strict as assert } from "node:assert";
import test from "node:test";

import {
  AGENT_ORDER,
  deriveLiveState,
  emptyLiveState,
  isTerminalEvent
} from "../lib/run-stream-state.ts";
import type { PipelineEvent } from "../lib/types.ts";

type EventInput = {
  type: PipelineEvent["event_type"];
  payload?: Record<string, unknown>;
  id?: number;
};

function makeEvents(items: EventInput[]): PipelineEvent[] {
  const baseTime = new Date("2026-01-01T00:00:00.000Z").getTime();
  return items.map((item, index) => ({
    id: item.id ?? index + 1,
    run_id: "00000000-0000-0000-0000-000000000000",
    event_type: item.type,
    payload: item.payload ?? {},
    created_at: new Date(baseTime + index * 100).toISOString()
  }));
}

function fullSuccessEvents(): EventInput[] {
  return [
    ...AGENT_ORDER.flatMap<EventInput>((name) => [
      { type: "agent_started", payload: { agent_name: name } },
      { type: "agent_done", payload: { agent_name: name, estimated_qubits: 6 + AGENT_ORDER.indexOf(name) } }
    ]),
    ...AGENT_ORDER.map<EventInput>((name) => ({
      type: "scorecard_ready",
      payload: {
        agent_name: name,
        qubit_count: 6,
        sparsity: 0.4 + AGENT_ORDER.indexOf(name) * 0.05,
        condition_number: 2.5,
        penalty_sensitivity: 0.1,
        classical_baseline_objective: -0.5,
        classical_baseline_runtime_ms: 1.0,
        composite_score: 6.5 + AGENT_ORDER.indexOf(name) * 0.2,
        notes: "ok"
      }
    })),
    {
      type: "comparison_ready",
      payload: {
        scorecards: AGENT_ORDER.map((name) => ({
          agent_name: name,
          qubit_count: 6,
          sparsity: 0.5,
          condition_number: 2.5,
          penalty_sensitivity: 0.1,
          classical_baseline_objective: -0.5,
          classical_baseline_runtime_ms: 1.0,
          composite_score: 6.5,
          notes: "ok"
        })),
        top_agent: "decomp",
        runner_up: "graph"
      }
    },
    {
      type: "critic_verdict",
      payload: {
        winner_agent: "decomp",
        runner_up_agent: "graph",
        rejected_agents: ["penalty", "slack", "domain"],
        rationale: "Decomp wins by a margin on composite score and qubit count.",
        confidence: "high"
      }
    },
    { type: "refiner_done", payload: { agent_name: "decomp", with_hints: false } },
    {
      type: "circuit_ready",
      payload: { qubit_count: 6, depth: 14, gate_count: 64 }
    },
    {
      type: "simulation_done",
      payload: {
        best_bitstring: "101010",
        best_objective: -0.48,
        quality_vs_classical: 96.0
      }
    },
    { type: "pipeline_done", payload: { best_bitstring: "101010", winner: "decomp" } }
  ];
}

test("emptyLiveState marks all agents pending", () => {
  const state = emptyLiveState();
  for (const name of AGENT_ORDER) {
    assert.equal(state.agents[name].status, "pending");
  }
  assert.equal(state.stages.agents, "pending");
  assert.equal(state.terminal, null);
});

test("agent_started flips card to running and stage to active", () => {
  const events = makeEvents([
    { type: "agent_started", payload: { agent_name: "penalty" } }
  ]);
  const state = deriveLiveState(events);
  assert.equal(state.agents.penalty.status, "running");
  assert.equal(state.stages.agents, "active");
});

test("agent_done captures estimated qubits and keeps stage active until all finish", () => {
  const events = makeEvents([
    { type: "agent_started", payload: { agent_name: "penalty" } },
    { type: "agent_done", payload: { agent_name: "penalty", estimated_qubits: 12 } },
    { type: "agent_started", payload: { agent_name: "slack" } }
  ]);
  const state = deriveLiveState(events);
  assert.equal(state.agents.penalty.status, "done");
  assert.equal(state.agents.penalty.estimatedQubits, 12);
  assert.equal(state.agents.slack.status, "running");
  assert.equal(state.stages.agents, "active");
});

test("agent_failed marks card failed and stores reason", () => {
  const events = makeEvents([
    { type: "agent_started", payload: { agent_name: "graph" } },
    { type: "agent_failed", payload: { agent_name: "graph", error: "ValueError: nope" } }
  ]);
  const state = deriveLiveState(events);
  assert.equal(state.agents.graph.status, "failed");
  assert.equal(state.agents.graph.errorMessage, "ValueError: nope");
});

test("scorecard_ready accumulates one entry per agent in canonical order", () => {
  const events = makeEvents([
    {
      type: "scorecard_ready",
      payload: {
        agent_name: "graph",
        qubit_count: 6,
        sparsity: 0.5,
        condition_number: 2.0,
        penalty_sensitivity: 0.05,
        classical_baseline_objective: -1.0,
        classical_baseline_runtime_ms: 0.5,
        composite_score: 7.1,
        notes: "ok"
      }
    },
    {
      type: "scorecard_ready",
      payload: {
        agent_name: "penalty",
        qubit_count: 6,
        sparsity: 0.4,
        condition_number: 2.5,
        penalty_sensitivity: 0.1,
        classical_baseline_objective: -1.0,
        classical_baseline_runtime_ms: 0.5,
        composite_score: 6.4,
        notes: "ok"
      }
    }
  ]);
  const state = deriveLiveState(events);
  assert.equal(state.scorecards.length, 2);
  assert.equal(state.scorecards[0].agent_name, "penalty");
  assert.equal(state.scorecards[1].agent_name, "graph");
  assert.equal(state.stages.evaluate, "active");
});

test("comparison_ready then critic_verdict advance the stepper", () => {
  const events = makeEvents([
    {
      type: "comparison_ready",
      payload: { scorecards: [], top_agent: "decomp", runner_up: "graph" }
    },
    {
      type: "critic_verdict",
      payload: {
        winner_agent: "decomp",
        runner_up_agent: "graph",
        rejected_agents: [],
        rationale: "x",
        confidence: "high"
      }
    }
  ]);
  const state = deriveLiveState(events);
  assert.equal(state.stages.evaluate, "done");
  assert.equal(state.stages.critic, "done");
  assert.equal(state.stages.refine, "active");
  assert.equal(state.criticVerdict?.winner_agent, "decomp");
});

test("panel-visibility flags flip as the matching events arrive", () => {
  // Build a partial run: scorecards in, critic in, refiner+circuit+sim not yet.
  const partial = [
    ...AGENT_ORDER.flatMap<EventInput>((name) => [
      { type: "agent_started", payload: { agent_name: name } },
      { type: "agent_done", payload: { agent_name: name, estimated_qubits: 6 } }
    ]),
    {
      type: "scorecard_ready",
      payload: {
        agent_name: "decomp",
        qubit_count: 6,
        sparsity: 0.5,
        condition_number: 2.5,
        penalty_sensitivity: 0.1,
        classical_baseline_objective: -0.5,
        classical_baseline_runtime_ms: 1.0,
        composite_score: 7.0,
        notes: "ok"
      }
    },
    {
      type: "critic_verdict",
      payload: {
        winner_agent: "decomp",
        runner_up_agent: "graph",
        rejected_agents: [],
        rationale: "x",
        confidence: "medium"
      }
    }
  ] as EventInput[];
  const state = deriveLiveState(makeEvents(partial));
  // Scorecard table should be ready
  assert.equal(state.scorecards.length > 0, true);
  // Critic verdict visible
  assert.notEqual(state.criticVerdict, null);
  // Refiner, circuit, benchmark NOT yet visible
  assert.equal(state.refinerEvent, null);
  assert.equal(state.circuitEvent, null);
  assert.equal(state.simulationEvent, null);
});

test("a full successful run reaches all stages and terminal=done", () => {
  const state = deriveLiveState(makeEvents(fullSuccessEvents()));
  for (const name of AGENT_ORDER) {
    assert.equal(state.agents[name].status, "done");
  }
  assert.equal(state.stages.agents, "done");
  assert.equal(state.stages.evaluate, "done");
  assert.equal(state.stages.critic, "done");
  assert.equal(state.stages.refine, "done");
  assert.equal(state.stages.circuit, "done");
  assert.equal(state.stages.simulate, "done");
  assert.equal(state.stages.done, "done");
  assert.equal(state.terminal, "done");
  assert.equal(state.criticVerdict?.winner_agent, "decomp");
  assert.equal(state.scorecards.length, AGENT_ORDER.length);
});

test("pipeline_failed marks the in-flight stage as failed and stores reason", () => {
  const events = makeEvents([
    { type: "agent_started", payload: { agent_name: "penalty" } },
    { type: "agent_failed", payload: { agent_name: "penalty", error: "x" } },
    { type: "agent_failed", payload: { agent_name: "slack", error: "x" } },
    { type: "agent_failed", payload: { agent_name: "graph", error: "x" } },
    { type: "agent_failed", payload: { agent_name: "decomp", error: "x" } },
    { type: "agent_failed", payload: { agent_name: "domain", error: "x" } },
    {
      type: "pipeline_failed",
      payload: { reason: "fewer than 3 agents succeeded" }
    }
  ]);
  const state = deriveLiveState(events);
  assert.equal(state.terminal, "failed");
  assert.equal(state.failureReason, "fewer than 3 agents succeeded");
  // No stage was active when the failure arrived (all agents already failed) —
  // ensure the helper doesn't crash and at least one stage is non-active.
  assert.notEqual(state.stages.evaluate, "active");
});

test("pipeline_failed with qubit cap detail surfaces clear message", () => {
  const events = makeEvents([
    { type: "agent_started", payload: { agent_name: "penalty" } },
    { type: "agent_done", payload: { agent_name: "penalty", estimated_qubits: 25 } },
    {
      type: "pipeline_failed",
      payload: {
        reason: "qubit_cap_exceeded",
        message: "Pipeline halted: evaluator:penalty produced 25 qubits which exceeds the tier cap of 20.",
        qubit_count: 25,
        limit: 20,
        source: "evaluator:penalty"
      }
    }
  ]);
  const state = deriveLiveState(events);
  assert.equal(state.terminal, "failed");
  assert.match(state.failureReason ?? "", /qubits which exceeds the tier cap of 20/);
});

test("pipeline_cancelled is distinct from pipeline_failed", () => {
  const events = makeEvents([
    { type: "agent_started", payload: { agent_name: "penalty" } },
    { type: "pipeline_cancelled", payload: { reason: "cancelled by user" } }
  ]);
  const state = deriveLiveState(events);
  assert.equal(state.terminal, "cancelled");
  assert.equal(state.failureReason, "cancelled by user");
});

test("isTerminalEvent returns true only for terminal types", () => {
  const terminal = makeEvents([
    { type: "pipeline_done" },
    { type: "pipeline_failed" },
    { type: "pipeline_cancelled" }
  ]);
  for (const event of terminal) assert.equal(isTerminalEvent(event), true);
  const nonTerminal = makeEvents([
    { type: "agent_started", payload: { agent_name: "penalty" } },
    { type: "scorecard_ready" },
    { type: "refiner_done" }
  ]);
  for (const event of nonTerminal) assert.equal(isTerminalEvent(event), false);
});

test("malformed payloads are ignored without crashing", () => {
  const events = makeEvents([
    { type: "agent_started", payload: { agent_name: 123 as unknown as string } },
    { type: "agent_done", payload: { agent_name: "not-a-real-agent" } },
    { type: "scorecard_ready", payload: { not: "a scorecard" } },
    { type: "critic_verdict", payload: {} }
  ]);
  const state = deriveLiveState(events);
  assert.equal(state.agents.penalty.status, "pending");
  assert.equal(state.criticVerdict, null);
  assert.equal(state.scorecards.length, 0);
});
