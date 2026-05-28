"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { PipelineEvent, RefinedQUBO } from "@/lib/types";

type Props = {
  refined: RefinedQUBO | null;
  refinerEvent: PipelineEvent | null;
};

const NO_CHANGE_TOKENS = new Set([
  "no improvement",
  "no improvements",
  "no improvements made",
  "none",
  "no changes"
]);

export function RefinerPanel({ refined, refinerEvent }: Props) {
  if (refined === null && refinerEvent === null) return null;

  const improvements = (refined?.improvements_made ?? []).filter((line) => line.trim().length > 0);
  const honestNoChange =
    refined !== null &&
    (improvements.length === 0 ||
      improvements.every((line) => NO_CHANGE_TOKENS.has(line.trim().toLowerCase())));

  const withHints =
    typeof refinerEvent?.payload?.with_hints === "boolean"
      ? Boolean(refinerEvent.payload.with_hints)
      : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Refiner</CardTitle>
        <CardDescription>
          {refined
            ? `Refined formulation derived from ${refined.original_agent}.`
            : "Refiner is finalising the winning formulation."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {refined === null ? (
          <p className="text-sm text-muted-foreground">Refiner finished — full details arrive when the run completes.</p>
        ) : honestNoChange ? (
          <div className="rounded-md border border-dashed bg-muted/40 p-3 text-sm">
            <p className="font-medium">No changes were necessary.</p>
            <p className="mt-1 text-muted-foreground">
              The original winning formulation was already strong — the refiner left it unchanged
              rather than introducing speculative tweaks.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Improvements made</h3>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {improvements.map((line, index) => (
                <li key={`${index}-${line.slice(0, 24)}`}>{line}</li>
              ))}
            </ul>
            {refined.expected_improvement ? (
              <p className="rounded-md bg-muted p-3 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">Expected effect: </span>
                {refined.expected_improvement}
              </p>
            ) : null}
          </div>
        )}

        {withHints === true ? (
          <p className="text-[11px] uppercase tracking-wider text-warning">
            Hint-driven pass — composite score was below the confidence threshold on the first try.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
