import { strict as assert } from "node:assert";
import test from "node:test";

import {
  advanceCountdown,
  classifyApiStatus,
  describeApiError,
  formatRetryAfter,
  parseRetryAfterSeconds
} from "../lib/error-state.ts";

test("classifyApiStatus maps statuses to error kinds", () => {
  assert.equal(classifyApiStatus(null), "network");
  assert.equal(classifyApiStatus(401), "auth");
  assert.equal(classifyApiStatus(403), "auth");
  assert.equal(classifyApiStatus(404), "not_found");
  assert.equal(classifyApiStatus(422), "validation");
  assert.equal(classifyApiStatus(429), "rate_limit");
  assert.equal(classifyApiStatus(503), "service_busy");
  assert.equal(classifyApiStatus(500), "server");
  assert.equal(classifyApiStatus(502), "server");
  assert.equal(classifyApiStatus(418), "unknown");
});

test("parseRetryAfterSeconds handles integer seconds and HTTP dates", () => {
  assert.equal(parseRetryAfterSeconds("30"), 30);
  assert.equal(parseRetryAfterSeconds("0"), 1);
  assert.equal(parseRetryAfterSeconds(null), 30);
  assert.equal(parseRetryAfterSeconds(""), 30);
  assert.equal(parseRetryAfterSeconds("not-a-number"), 30);
  const future = new Date("2030-01-01T00:01:00.000Z");
  const now = new Date("2030-01-01T00:00:00.000Z");
  assert.equal(parseRetryAfterSeconds(future.toUTCString(), now), 60);
});

test("formatRetryAfter pretty-prints seconds, minutes, and remainders", () => {
  assert.equal(formatRetryAfter(15), "15s");
  assert.equal(formatRetryAfter(60), "1m");
  assert.equal(formatRetryAfter(90), "1m 30s");
  assert.equal(formatRetryAfter(0), "0s");
  // Clamps negatives to zero.
  assert.equal(formatRetryAfter(-12), "0s");
});

test("describeApiError surfaces retry-after countdown in rate-limit toasts", () => {
  const toast = describeApiError(429, 45, null);
  assert.equal(toast.title, "Run limit reached");
  assert.match(toast.description, /45s/);
  assert.equal(toast.retryable, true);
});

test("describeApiError covers the network branch when status is null", () => {
  const toast = describeApiError(null, null, null);
  assert.equal(toast.title, "Network error");
  assert.match(toast.description.toLowerCase(), /connection/);
  assert.equal(toast.retryable, true);
});

test("describeApiError respects validation detail strings", () => {
  const toast = describeApiError(422, null, { detail: "must be a binary" });
  assert.equal(toast.title, "Invalid request");
  assert.match(toast.description, /binary/);
  assert.equal(toast.retryable, false);
});

test("describeApiError uses service_busy copy for 503", () => {
  const toast = describeApiError(503, 30, null);
  assert.equal(toast.title, "System busy");
  assert.match(toast.description, /30s/);
});

test("advanceCountdown decrements toward zero and flips done", () => {
  let state = advanceCountdown(3);
  assert.equal(state.secondsRemaining, 2);
  assert.equal(state.done, false);
  state = advanceCountdown(state.secondsRemaining);
  assert.equal(state.secondsRemaining, 1);
  state = advanceCountdown(state.secondsRemaining);
  assert.equal(state.secondsRemaining, 0);
  assert.equal(state.done, true);
  // Idempotent at zero.
  state = advanceCountdown(state.secondsRemaining);
  assert.equal(state.secondsRemaining, 0);
  assert.equal(state.done, true);
});
