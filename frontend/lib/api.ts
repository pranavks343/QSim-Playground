"use client";

import { toast } from "sonner";
import { z } from "zod";

import { describeApiError, parseRetryAfterSeconds } from "@/lib/error-state";
import { createClient } from "@/lib/supabase/client";
import {
  createRunResponseSchema,
  parseValidateResponseSchema,
  pdfExportResponseSchema,
  pipelineEventSchema,
  profileSchema,
  problemIRSchema,
  runSchema,
  shareToggleResponseSchema,
  sharedRunSchema,
  templateMetadataSchema,
  type CreateRunResponse,
  type ExportFormat,
  type ParseValidateResponse,
  type PdfExportResponse,
  type PipelineEvent,
  type Profile,
  type ProblemIR,
  type Run,
  type SharedRun,
  type ShareToggleResponse,
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

export class AuthRequiredError extends ApiError {
  constructor(detail: unknown, retryAfter: string | null) {
    super("Authentication required", 401, detail, retryAfter);
    this.name = "AuthRequiredError";
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

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body)
    });
  } catch (err) {
    const toastInfo = describeApiError(null, null, null);
    toast.error(toastInfo.title, { description: toastInfo.description });
    throw new ApiError(
      err instanceof Error ? err.message : "Network error",
      0,
      null,
      null
    );
  }

  const text = await response.text();
  const payload: unknown = text ? safeJsonParse(text) : null;

  if (!response.ok) {
    const retryAfterHeader = response.headers.get("retry-after");
    const retryAfterSeconds = retryAfterHeader
      ? parseRetryAfterSeconds(retryAfterHeader)
      : null;
    if (response.status === 401) {
      throw new AuthRequiredError(payload, retryAfterHeader);
    }
    // Skip the toast for 404 here — pages render their own "not found" UI.
    if (response.status !== 404) {
      const toastInfo = describeApiError(response.status, retryAfterSeconds, payload);
      toast.error(toastInfo.title, { description: toastInfo.description });
    }
    throw new ApiError(
      "API request failed",
      response.status,
      payload,
      retryAfterHeader
    );
  }

  return schema.parse(payload);
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
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

export async function fetchExportPdfPayload(runId: string): Promise<PdfExportResponse> {
  return apiFetch(`/api/runs/${runId}/export`, pdfExportResponseSchema, {
    method: "POST",
    body: { format: "pdf" }
  });
}

export async function downloadExportFile(
  runId: string,
  format: Exclude<ExportFormat, "pdf">
): Promise<{ blob: Blob; filename: string }> {
  const supabase = createClient();
  const {
    data: { session }
  } = await supabase.auth.getSession();
  const headers = new Headers({ "Content-Type": "application/json", Accept: "*/*" });
  if (session?.access_token) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }
  const response = await fetch(`${API_URL}/api/runs/${runId}/export`, {
    method: "POST",
    headers,
    body: JSON.stringify({ format })
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(
      "Export failed",
      response.status,
      detail,
      response.headers.get("retry-after")
    );
  }
  const filename = parseFilenameFromContentDisposition(
    response.headers.get("content-disposition")
  );
  const blob = await response.blob();
  return { blob, filename: filename ?? defaultExportFilename(runId, format) };
}

function parseFilenameFromContentDisposition(value: string | null): string | null {
  if (value === null) return null;
  const match = /filename="([^"]+)"/.exec(value);
  return match ? match[1] : null;
}

function defaultExportFilename(runId: string, format: ExportFormat): string {
  const extension = format === "notebook" ? "ipynb" : format === "script" ? "py" : "json";
  return `qsim_run_${runId.slice(0, 8)}.${extension}`;
}

export function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

export async function toggleShare(
  runId: string,
  shared: boolean
): Promise<ShareToggleResponse> {
  return apiFetch(`/api/runs/${runId}/share`, shareToggleResponseSchema, {
    method: "POST",
    body: { shared }
  });
}

export async function getSharedRun(runId: string): Promise<SharedRun> {
  return apiFetch(`/api/share/${runId}`, sharedRunSchema);
}
