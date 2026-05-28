"use client";

import type { RealtimeChannel } from "@supabase/supabase-js";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getRun, getRunEvents } from "@/lib/api";
import { isTerminalEvent } from "@/lib/run-stream-state";
import { createClient } from "@/lib/supabase/client";
import { pipelineEventSchema, type PipelineEvent, type Run } from "@/lib/types";

export type ConnectionStatus = "connecting" | "live" | "polling" | "closed";

export type UseRunStreamOptions = {
  runId: string;
  initialRun: Run;
  initialEvents: PipelineEvent[];
  pollingIntervalMs?: number;
};

export type UseRunStreamResult = {
  run: Run;
  events: PipelineEvent[];
  connection: ConnectionStatus;
};

const DEFAULT_POLLING_INTERVAL_MS = 3000;

function eventKey(event: PipelineEvent): string {
  if (typeof event.id === "number") return `id:${event.id}`;
  return `${event.event_type}:${event.created_at ?? event.timestamp ?? ""}`;
}

function dedupeAppend(existing: PipelineEvent[], incoming: PipelineEvent[]): PipelineEvent[] {
  if (incoming.length === 0) return existing;
  const seen = new Set(existing.map(eventKey));
  const additions: PipelineEvent[] = [];
  for (const event of incoming) {
    const key = eventKey(event);
    if (seen.has(key)) continue;
    seen.add(key);
    additions.push(event);
  }
  if (additions.length === 0) return existing;
  return [...existing, ...additions].sort(sortByOrdering);
}

function sortByOrdering(a: PipelineEvent, b: PipelineEvent): number {
  if (typeof a.id === "number" && typeof b.id === "number") return a.id - b.id;
  const ta = a.created_at ?? a.timestamp ?? "";
  const tb = b.created_at ?? b.timestamp ?? "";
  return ta.localeCompare(tb);
}

function highestEventId(events: PipelineEvent[]): number | null {
  let max: number | null = null;
  for (const event of events) {
    if (typeof event.id === "number" && (max === null || event.id > max)) {
      max = event.id;
    }
  }
  return max;
}

export function useRunStream(options: UseRunStreamOptions): UseRunStreamResult {
  const { runId, initialRun, initialEvents, pollingIntervalMs = DEFAULT_POLLING_INTERVAL_MS } =
    options;

  const [run, setRun] = useState<Run>(initialRun);
  const [events, setEvents] = useState<PipelineEvent[]>(() =>
    dedupeAppend([], initialEvents)
  );
  const [connection, setConnection] = useState<ConnectionStatus>(() =>
    isTerminalRunStatus(initialRun.status) ? "closed" : "connecting"
  );

  const eventsRef = useRef<PipelineEvent[]>(events);
  const closedRef = useRef<boolean>(isTerminalRunStatus(initialRun.status));
  const finalRunFetchedRef = useRef<boolean>(false);
  const pollingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const channelRef = useRef<RealtimeChannel | null>(null);

  useEffect(() => {
    eventsRef.current = events;
  }, [events]);

  const stopPolling = useCallback(() => {
    if (pollingTimerRef.current !== null) {
      clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
  }, []);

  const fetchFinalRun = useCallback(async () => {
    if (finalRunFetchedRef.current) return;
    finalRunFetchedRef.current = true;
    try {
      const fresh = await getRun(runId);
      setRun(fresh);
    } catch (err) {
      // Stay with current state; caller can manually refresh.
      finalRunFetchedRef.current = false;
      // eslint-disable-next-line no-console
      console.warn("use-run-stream: failed to fetch final run", err);
    }
  }, [runId]);

  const handleIncoming = useCallback(
    (incoming: PipelineEvent[]) => {
      if (incoming.length === 0) return;
      setEvents((prev) => dedupeAppend(prev, incoming));
      for (const event of incoming) {
        if (isTerminalEvent(event)) {
          closedRef.current = true;
          stopPolling();
          if (channelRef.current !== null) {
            try {
              channelRef.current.unsubscribe();
            } catch {
              // ignore
            }
            channelRef.current = null;
          }
          setConnection("closed");
          void fetchFinalRun();
          break;
        }
      }
    },
    [fetchFinalRun, stopPolling]
  );

  const pollOnce = useCallback(async () => {
    if (closedRef.current) return;
    const afterEventId = highestEventId(eventsRef.current);
    try {
      const incoming = await getRunEvents(runId, {
        afterEventId: afterEventId === null ? undefined : afterEventId
      });
      handleIncoming(incoming);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("use-run-stream: poll failed", err);
    }
  }, [handleIncoming, runId]);

  const startPolling = useCallback(() => {
    stopPolling();
    if (closedRef.current) return;
    setConnection("polling");
    // Do an immediate catch-up so the UI does not wait a full interval.
    void pollOnce();
    pollingTimerRef.current = setInterval(() => {
      void pollOnce();
    }, pollingIntervalMs);
  }, [pollOnce, pollingIntervalMs, stopPolling]);

  useEffect(() => {
    if (closedRef.current) {
      // Already terminal — make sure the latest run is in memory.
      void fetchFinalRun();
      return () => undefined;
    }

    let supabase;
    try {
      supabase = createClient();
    } catch {
      // No Supabase env on this client — fall back to polling for the
      // whole lifetime of the page.
      startPolling();
      return () => {
        stopPolling();
      };
    }

    const channel = supabase
      .channel(`run-events:${runId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "run_events",
          filter: `run_id=eq.${runId}`
        },
        (payload: { new: unknown }) => {
          const parsed = pipelineEventSchema.safeParse(payload.new);
          if (parsed.success) {
            handleIncoming([parsed.data]);
          }
        }
      )
      .subscribe((status) => {
        if (closedRef.current) return;
        if (status === "SUBSCRIBED") {
          stopPolling();
          setConnection("live");
          // Catch up on anything emitted between the server-render and
          // the subscription becoming active.
          void pollOnce();
        } else if (
          status === "CHANNEL_ERROR" ||
          status === "TIMED_OUT" ||
          status === "CLOSED"
        ) {
          if (!closedRef.current) {
            startPolling();
          }
        }
      });

    channelRef.current = channel;

    return () => {
      stopPolling();
      try {
        channel.unsubscribe();
      } catch {
        // ignore
      }
      channelRef.current = null;
    };
  }, [
    fetchFinalRun,
    handleIncoming,
    pollOnce,
    runId,
    startPolling,
    stopPolling
  ]);

  // If the run already arrived in a terminal state from the server, make
  // sure the final fetch happens once on mount.
  useEffect(() => {
    if (isTerminalRunStatus(initialRun.status)) {
      void fetchFinalRun();
    }
  }, [fetchFinalRun, initialRun.status]);

  return useMemo(
    () => ({ run, events, connection }),
    [connection, events, run]
  );
}

function isTerminalRunStatus(status: Run["status"]): boolean {
  return status === "done" || status === "failed" || status === "cancelled" || status === "timeout";
}
