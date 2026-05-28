"use client";

import { redirect } from "next/navigation";
import { toast } from "sonner";
import { z } from "zod";

import { createClient } from "@/lib/supabase/client";
import {
  createRunResponseSchema,
  parseValidateResponseSchema,
  pipelineEventSchema,
  profileSchema,
  problemIRSchema,
  runSchema,
  templateMetadataSchema,
  type CreateRunResponse,
  type ParseValidateResponse,
  type PipelineEvent,
  type Profile,
  type ProblemIR,
  type Run,
  type TemplateMetadata
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
    readonly retryAfter: string | null
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

export async function apiFetch<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestOptions = {}
): Promise<T> {
  const supabase = createClient();
  const {
    data: { session }
  } = await supabase.auth.getSession();
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (session?.access_token) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body)
  });

  const text = await response.text();
  const payload: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const retryAfter = response.headers.get("retry-after");
    if (response.status === 401) {
      redirect("/login");
    }
    if (response.status === 429) {
      toast.error("Run limit reached", {
        description: retryAfter ? `Retry after ${retryAfter}s.` : "Try again later."
      });
    }
    throw new ApiError("API request failed", response.status, payload, retryAfter);
  }

  return schema.parse(payload);
}

export const runListSchema = z.object({
  items: z.array(runSchema),
  next_cursor: z.string().nullable().optional()
});

export const templatesResponseSchema = z.object({
  items: z.array(templateMetadataSchema)
});

export async function getTemplates(): Promise<TemplateMetadata[]> {
  return apiFetch("/api/templates", templatesResponseSchema).then((result) => result.items);
}

export async function getProfile(): Promise<Profile> {
  return apiFetch("/api/profile", profileSchema);
}

export async function getRun(runId: string): Promise<Run> {
  return apiFetch(`/api/runs/${runId}`, runSchema);
}

export const runEventsResponseSchema = z.object({
  items: z.array(pipelineEventSchema)
});

export async function getRunEvents(
  runId: string,
  options: { afterEventId?: number } = {}
): Promise<PipelineEvent[]> {
  const params = new URLSearchParams();
  if (options.afterEventId !== undefined) {
    params.set("after_event_id", String(options.afterEventId));
  }
  const query = params.toString();
  const path = query ? `/api/runs/${runId}/events?${query}` : `/api/runs/${runId}/events`;
  return apiFetch(path, runEventsResponseSchema).then((result) => result.items);
}

export async function getRuns(limit = 10): Promise<Run[]> {
  return apiFetch(`/api/runs?limit=${limit}`, runListSchema).then((result) => result.items);
}

export async function createTemplateRun(templateName: string): Promise<CreateRunResponse> {
  return apiFetch("/api/runs", createRunResponseSchema, {
    method: "POST",
    body: { input_source: "template", template_name: templateName }
  });
}

export async function createCodeRun(sourceCode: string): Promise<CreateRunResponse> {
  return apiFetch("/api/runs", createRunResponseSchema, {
    method: "POST",
    body: { input_source: "code", source_code: sourceCode }
  });
}

export async function createIrRun(problemIr: ProblemIR): Promise<CreateRunResponse> {
  return apiFetch("/api/runs", createRunResponseSchema, {
    method: "POST",
    body: { input_source: "ir", problem_ir: problemIRSchema.parse(problemIr) }
  });
}

export async function validateSourceCode(sourceCode: string): Promise<ParseValidateResponse> {
  return apiFetch("/api/parse/validate", parseValidateResponseSchema, {
    method: "POST",
    body: { source_code: sourceCode }
  });
}
