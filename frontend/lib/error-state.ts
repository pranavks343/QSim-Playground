// Pure, side-effect-free helpers used by API error handling. Kept in
// their own module so they can be unit-tested without a DOM or fetch.

export type ApiErrorKind =
  | "auth"
  | "rate_limit"
  | "service_busy"
  | "not_found"
  | "validation"
  | "server"
  | "network"
  | "unknown";

const RETRY_AFTER_FALLBACK_SECONDS = 30;

export function classifyApiStatus(status: number | null): ApiErrorKind {
  if (status === null) return "network";
  if (status === 401 || status === 403) return "auth";
  if (status === 404) return "not_found";
  if (status === 422) return "validation";
  if (status === 429) return "rate_limit";
  if (status === 503) return "service_busy";
  if (status >= 500) return "server";
  return "unknown";
}

export function parseRetryAfterSeconds(
  value: string | null,
  now: Date = new Date()
): number {
  if (value === null) return RETRY_AFTER_FALLBACK_SECONDS;
  const trimmed = value.trim();
  if (trimmed.length === 0) return RETRY_AFTER_FALLBACK_SECONDS;
  const asNumber = Number(trimmed);
  if (Number.isFinite(asNumber) && asNumber >= 0) {
    return Math.max(1, Math.round(asNumber));
  }
  const asDate = Date.parse(trimmed);
  if (!Number.isNaN(asDate)) {
    const delta = Math.round((asDate - now.getTime()) / 1000);
    return Math.max(1, delta);
  }
  return RETRY_AFTER_FALLBACK_SECONDS;
}

export function formatRetryAfter(seconds: number): string {
  const clamped = Math.max(0, Math.round(seconds));
  if (clamped < 60) return `${clamped}s`;
  const mins = Math.floor(clamped / 60);
  const remaining = clamped % 60;
  if (remaining === 0) return `${mins}m`;
  return `${mins}m ${remaining}s`;
}

export type ErrorToast = {
  title: string;
  description: string;
  retryable: boolean;
};

export function describeApiError(
  status: number | null,
  retryAfterSeconds: number | null,
  detail: unknown
): ErrorToast {
  const kind = classifyApiStatus(status);
  const detailMessage = extractDetailMessage(detail);
  switch (kind) {
    case "auth":
      return {
        title: "Session expired",
        description: "Sign in again to continue.",
        retryable: false
      };
    case "rate_limit":
      return {
        title: "Run limit reached",
        description:
          retryAfterSeconds !== null
            ? `Try again in ${formatRetryAfter(retryAfterSeconds)}.`
            : "Try again in a moment.",
        retryable: true
      };
    case "service_busy":
      return {
        title: "System busy",
        description:
          retryAfterSeconds !== null
            ? `Retry in ${formatRetryAfter(retryAfterSeconds)}.`
            : "Retry in about 30 seconds.",
        retryable: true
      };
    case "not_found":
      return {
        title: "Not found",
        description: detailMessage ?? "We couldn't find what you were looking for.",
        retryable: false
      };
    case "validation":
      return {
        title: "Invalid request",
        description: detailMessage ?? "The server rejected the payload — double-check your input.",
        retryable: false
      };
    case "network":
      return {
        title: "Network error",
        description: "Check your connection and try again.",
        retryable: true
      };
    case "server":
      return {
        title: "Something went wrong",
        description: detailMessage ?? "Our backend hit an error. Please retry shortly.",
        retryable: true
      };
    case "unknown":
    default:
      return {
        title: "Request failed",
        description:
          detailMessage ??
          (status === null
            ? "Something went wrong. Please try again."
            : `HTTP ${status} — please try again.`),
        retryable: status === null || (status >= 500 && status < 600)
      };
  }
}

function extractDetailMessage(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim().length > 0) {
    return detail.trim();
  }
  if (detail !== null && typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.detail === "string") return obj.detail;
    if (typeof obj.message === "string") return obj.message;
  }
  return null;
}

export type RetryCountdown = {
  secondsRemaining: number;
  done: boolean;
  formatted: string;
};

export function advanceCountdown(secondsRemaining: number): RetryCountdown {
  const next = Math.max(0, secondsRemaining - 1);
  return {
    secondsRemaining: next,
    done: next === 0,
    formatted: formatRetryAfter(next)
  };
}
