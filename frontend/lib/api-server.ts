import { z } from "zod";

import { createClient } from "@/lib/supabase/server";
import {
  pipelineEventSchema,
  runSchema,
  sharedRunSchema,
  type PipelineEvent,
  type Run,
  type SharedRun
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ServerFetchError = {
  status: number;
  message: string;
};

const runEventsResponseSchema = z.object({
  items: z.array(pipelineEventSchema)
});

async function getBearerToken(): Promise<string | null> {
  const client = createClient();
  if (client === null) return null;
  const {
    data: { session }
  } = await client.auth.getSession();
  return session?.access_token ?? null;
}

async function fetchWithAuth<T>(
  path: string,
  schema: z.ZodType<T>
): Promise<T | ServerFetchError> {
  const token = await getBearerToken();
  if (token === null) {
    return { status: 401, message: "Not authenticated" };
  }
  const response = await fetch(`${API_URL}${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json"
    },
    cache: "no-store"
  });
  const text = await response.text();
  if (!response.ok) {
    return { status: response.status, message: text || response.statusText };
  }
  const json: unknown = text ? JSON.parse(text) : null;
  return schema.parse(json);
}

export async function fetchRunInitial(
  runId: string
): Promise<{ run: Run; events: PipelineEvent[] } | ServerFetchError> {
  const runResult = await fetchWithAuth(`/api/runs/${runId}`, runSchema);
  if (isError(runResult)) return runResult;
  const eventsResult = await fetchWithAuth(
    `/api/runs/${runId}/events`,
    runEventsResponseSchema
  );
  if (isError(eventsResult)) return eventsResult;
  return { run: runResult, events: eventsResult.items };
}

export async function fetchSharedRun(
  runId: string
): Promise<SharedRun | ServerFetchError> {
  const response = await fetch(`${API_URL}/api/share/${runId}`, {
    headers: { Accept: "application/json" },
    cache: "no-store"
  });
  const text = await response.text();
  if (!response.ok) {
    return { status: response.status, message: text || response.statusText };
  }
  const json: unknown = text ? JSON.parse(text) : null;
  return sharedRunSchema.parse(json);
}

export function isError(value: unknown): value is ServerFetchError {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    "message" in value
  );
}
