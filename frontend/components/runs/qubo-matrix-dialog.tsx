"use client";

import { useMemo } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import type { QUBOOutput } from "@/lib/types";
import { cn } from "@/lib/utils";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  qubo: QUBOOutput | null;
};

export function QuboMatrixDialog({ open, onOpenChange, qubo }: Props) {
  const matrix = qubo?.q_matrix ?? null;
  const variables = qubo?.variable_order ?? null;

  const maxAbs = useMemo(() => {
    if (matrix === null) return 0;
    let best = 0;
    for (const row of matrix) {
      for (const value of row) {
        const abs = Math.abs(value);
        if (abs > best) best = abs;
      }
    }
    return best;
  }, [matrix]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{qubo ? `${labelFor(qubo.agent_name)} QUBO` : "QUBO"}</DialogTitle>
          {qubo ? (
            <DialogDescription>
              {qubo.strategy}
            </DialogDescription>
          ) : null}
        </DialogHeader>
        {matrix !== null && variables !== null ? (
          <div className="space-y-4 overflow-x-auto">
            <div className="text-xs text-muted-foreground">
              Cell shading shows magnitude relative to the largest absolute coefficient
              (|max| = {maxAbs.toFixed(3)}). Negative coefficients use a different hue.
            </div>
            <div
              className="grid gap-px rounded-md border bg-border text-[10px]"
              style={{
                gridTemplateColumns: `minmax(3rem, auto) repeat(${variables.length}, minmax(2.25rem, 1fr))`
              }}
            >
              <div className="bg-card p-1" aria-hidden />
              {variables.map((name) => (
                <div
                  key={`col-${name}`}
                  className="bg-card p-1 text-center font-mono text-[10px] text-muted-foreground"
                  title={name}
                >
                  {name}
                </div>
              ))}
              {matrix.map((row, rowIndex) => (
                <RowCells
                  key={`row-${variables[rowIndex] ?? rowIndex}`}
                  variableName={variables[rowIndex] ?? `r${rowIndex}`}
                  row={row}
                  maxAbs={maxAbs}
                />
              ))}
            </div>
            <section className="space-y-2">
              <h3 className="text-sm font-semibold">Justification</h3>
              <p className="whitespace-pre-line text-sm text-muted-foreground">
                {qubo?.justification}
              </p>
            </section>
            {qubo && Object.keys(qubo.parameters_used ?? {}).length > 0 ? (
              <section className="space-y-2">
                <h3 className="text-sm font-semibold">Parameters</h3>
                <ul className="grid grid-cols-2 gap-1 text-xs text-muted-foreground">
                  {Object.entries(qubo.parameters_used).map(([key, value]) => (
                    <li key={key} className="rounded bg-muted px-2 py-1">
                      <span className="font-mono">{key}</span>: {String(value)}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">QUBO data is not yet available.</p>
        )}
      </DialogContent>
    </Dialog>
  );
}

function RowCells({
  variableName,
  row,
  maxAbs
}: {
  variableName: string;
  row: number[];
  maxAbs: number;
}) {
  return (
    <>
      <div className="bg-card p-1 text-right font-mono text-[10px] text-muted-foreground" title={variableName}>
        {variableName}
      </div>
      {row.map((value, colIndex) => (
        <div
          key={colIndex}
          className={cn(
            "p-1 text-center font-mono text-[10px]",
            cellTextClass(value),
            "bg-card"
          )}
          style={{ background: cellBackground(value, maxAbs) }}
          title={`${variableName} · col ${colIndex}: ${value}`}
        >
          {Math.abs(value) <= 1e-9 ? "·" : formatNumber(value)}
        </div>
      ))}
    </>
  );
}

function cellBackground(value: number, maxAbs: number): string {
  if (maxAbs <= 0 || Math.abs(value) <= 1e-9) {
    return "hsl(var(--card))";
  }
  const intensity = Math.min(1, Math.abs(value) / maxAbs);
  if (value > 0) {
    // primary blue
    return `hsla(226, 70%, 50%, ${0.15 + intensity * 0.55})`;
  }
  // amber for negative
  return `hsla(38, 92%, 55%, ${0.15 + intensity * 0.55})`;
}

function cellTextClass(value: number): string {
  if (Math.abs(value) <= 1e-9) return "text-muted-foreground";
  return "text-foreground";
}

function formatNumber(value: number): string {
  if (Math.abs(value) >= 100) return value.toFixed(0);
  if (Math.abs(value) >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

function labelFor(agentName: string): string {
  return agentName.charAt(0).toUpperCase() + agentName.slice(1);
}
