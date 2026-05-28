import { z } from "zod";

// Keep these schemas in lockstep with backend/core/ir_schema.json and backend/api/schemas.py.

export const variableTypeSchema = z.enum(["binary", "integer", "continuous"]);
export const constraintTypeSchema = z.enum(["<=", ">=", "="]);
export const objectiveSenseSchema = z.enum(["minimize", "maximize"]);

export const variableSchema = z.object({
  name: z.string().regex(/^[a-zA-Z_][a-zA-Z0-9_]*$/),
  type: variableTypeSchema,
  lower_bound: z.number().nullable().optional(),
  upper_bound: z.number().nullable().optional()
});

export const constraintSchema = z.object({
  name: z.string().nullable().optional(),
  linear_terms: z.record(z.string(), z.number()),
  quadratic_terms: z.record(z.string(), z.number()).optional(),
  type: constraintTypeSchema,
  rhs: z.number()
});

export const objectiveSchema = z.object({
  sense: objectiveSenseSchema,
  linear_terms: z.record(z.string(), z.number()).optional(),
  quadratic_terms: z.record(z.string(), z.number()).optional(),
  constant: z.number().optional()
});

export const problemIRSchema = z.object({
  name: z.string(),
  description: z.string().optional(),
  variables: z.array(variableSchema).min(1),
  objective: objectiveSchema,
  constraints: z.array(constraintSchema).optional(),
  metadata: z.record(z.string(), z.unknown()).optional()
});

export const quboOutputSchema = z.object({
  agent_name: z.string(),
  strategy: z.string(),
  q_matrix: z.array(z.array(z.number())),
  variable_order: z.array(z.string()),
  parameters_used: z.record(z.string(), z.unknown()),
  justification: z.string(),
  estimated_qubits: z.number().int()
});

export const scorecardSchema = z.object({
  agent_name: z.string(),
  qubit_count: z.number().int(),
  sparsity: z.number(),
  condition_number: z.number(),
  penalty_sensitivity: z.number(),
  classical_baseline_objective: z.number(),
  classical_baseline_runtime_ms: z.number(),
  composite_score: z.number(),
  notes: z.string()
});

export const comparisonTableSchema = z.object({
  scorecards: z.array(scorecardSchema),
  top_agent: z.string(),
  runner_up: z.string()
});

export const criticVerdictSchema = z.object({
  winner_agent: z.string(),
  runner_up_agent: z.string(),
  rejected_agents: z.array(z.string()),
  rationale: z.string(),
  confidence: z.enum(["high", "medium", "low"])
});

export const refinedQuboSchema = quboOutputSchema.extend({
  original_agent: z.string(),
  improvements_made: z.array(z.string()),
  expected_improvement: z.string()
});

export const circuitDataSchema = z.object({
  qubit_count: z.number().int(),
  depth: z.number().int(),
  gate_count: z.number().int(),
  reps: z.number().int(),
  qiskit_qasm: z.string(),
  circuit_image_svg: z.string().nullable().optional()
});

export const simulationResultSchema = z.object({
  best_bitstring: z.string(),
  best_objective: z.number(),
  quality_vs_classical: z.number(),
  top_5_bitstrings: z.array(z.tuple([z.string(), z.number().int(), z.number()])),
  total_shots: z.number().int(),
  runtime_ms: z.number()
});

export const classicalResultSchema = z.object({
  best_bitstring: z.string(),
  best_objective: z.number(),
  runtime_ms: z.number(),
  method: z.string()
});

export const pipelineEventSchema = z.object({
  id: z.number().int().optional(),
  run_id: z.string(),
  event_type: z.string(),
  payload: z.record(z.string(), z.unknown()),
  created_at: z.string().optional(),
  timestamp: z.string().optional()
});

export const runStatusSchema = z.enum(["queued", "running", "done", "failed", "timeout", "cancelled"]);
export const inputSourceSchema = z.enum(["template", "code", "ir"]);

export const runSchema = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  status: runStatusSchema,
  template: z.string().nullable().optional(),
  input_source: inputSourceSchema,
  problem_ir: problemIRSchema,
  qubos: z.record(z.string(), quboOutputSchema).nullable().optional(),
  scorecards: z.record(z.string(), scorecardSchema).nullable().optional(),
  winner_agent: z.string().nullable().optional(),
  critic_verdict: criticVerdictSchema.nullable().optional(),
  refined_qubo: refinedQuboSchema.nullable().optional(),
  circuit_data: circuitDataSchema.nullable().optional(),
  sim_result: simulationResultSchema.nullable().optional(),
  classical_result: classicalResultSchema.nullable().optional(),
  error: z.string().nullable().optional(),
  total_runtime_ms: z.number().int().nullable().optional(),
  cancel_requested: z.boolean().optional(),
  created_at: z.string(),
  completed_at: z.string().nullable().optional(),
  deleted_at: z.string().nullable().optional()
});

export const templateMetadataSchema = z.object({
  name: z.string(),
  display_name: z.string(),
  description: z.string(),
  difficulty: z.enum(["easy", "medium", "hard"]),
  variable_count: z.number().int(),
  constraint_count: z.number().int(),
  expected_optimal_value: z.number().nullable(),
  domain_tags: z.array(z.string())
});

export const profileSchema = z.object({
  id: z.string().uuid(),
  email: z.string(),
  tier: z.string(),
  monthly_runs_used: z.number().int(),
  monthly_runs_limit: z.number().int(),
  quota_remaining: z.number().int(),
  quota_resets_at: z.string().nullable().optional()
});

export const createRunResponseSchema = z.object({
  run_id: z.string().uuid(),
  status: z.literal("queued")
});

export const parseErrorSchema = z.object({
  message: z.string(),
  line: z.number().int().nullable().optional(),
  column: z.number().int().nullable().optional()
});

export const parseValidateResponseSchema = z.object({
  ok: z.boolean(),
  ir: problemIRSchema.nullable().optional(),
  errors: z.array(parseErrorSchema)
});

export type ProblemIR = z.infer<typeof problemIRSchema>;
export type QUBOOutput = z.infer<typeof quboOutputSchema>;
export type Scorecard = z.infer<typeof scorecardSchema>;
export type ComparisonTable = z.infer<typeof comparisonTableSchema>;
export type CriticVerdict = z.infer<typeof criticVerdictSchema>;
export type RefinedQUBO = z.infer<typeof refinedQuboSchema>;
export type CircuitData = z.infer<typeof circuitDataSchema>;
export type SimulationResult = z.infer<typeof simulationResultSchema>;
export type ClassicalResult = z.infer<typeof classicalResultSchema>;
export type PipelineEvent = z.infer<typeof pipelineEventSchema>;
export type Run = z.infer<typeof runSchema>;
export type TemplateMetadata = z.infer<typeof templateMetadataSchema>;
export type Profile = z.infer<typeof profileSchema>;
export type CreateRunResponse = z.infer<typeof createRunResponseSchema>;
export type ParseValidateResponse = z.infer<typeof parseValidateResponseSchema>;
