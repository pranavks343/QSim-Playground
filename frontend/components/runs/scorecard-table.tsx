"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { useMemo, useState } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from "@/components/ui/tooltip";
import type { Scorecard } from "@/lib/types";
import { cn } from "@/lib/utils";

type SortKey =
  | "agent_name"
  | "qubit_count"
  | "sparsity"
  | "condition_number"
  | "penalty_sensitivity"
  | "classical_baseline_objective"
  | "composite_score";

type Column = {
  key: SortKey;
  label: string;
  tooltip: string;
  align: "left" | "right";
  numeric: boolean;
  format: (sc: Scorecard) => string;
};

const COLUMNS: Column[] = [
  {
    key: "agent_name",
    label: "Agent",
    tooltip: "Specialist agent that produced this formulation.",
    align: "left",
    numeric: false,
    format: (sc) => sc.agent_name.charAt(0).toUpperCase() + sc.agent_name.slice(1)
  },
  {
    key: "qubit_count",
    label: "Qubits",
    tooltip: "Number of qubits the QAOA circuit will need. Smaller is cheaper to simulate.",
    align: "right",
    numeric: true,
    format: (sc) => String(sc.qubit_count)
  },
  {
    key: "sparsity",
    label: "Sparsity",
    tooltip: "Fraction of zero entries in the upper-triangular Q matrix. Sparser QUBOs build shallower circuits.",
    align: "right",
    numeric: true,
    format: (sc) => formatRatio(sc.sparsity)
  },
  {
    key: "condition_number",
    label: "Condition",
    tooltip: "Matrix condition number. Lower values are numerically more stable.",
    align: "right",
    numeric: true,
    format: (sc) => formatLargeNumber(sc.condition_number)
  },
  {
    key: "penalty_sensitivity",
    label: "Penalty sens.",
    tooltip: "How much the optimum shifts under ±10% penalty perturbation. Lower is more robust.",
    align: "right",
    numeric: true,
    format: (sc) => formatRatio(sc.penalty_sensitivity)
  },
  {
    key: "classical_baseline_objective",
    label: "Classical obj.",
    tooltip: "Objective value reached by the simulated-annealing baseline. The honesty anchor.",
    align: "right",
    numeric: true,
    format: (sc) => formatNumber(sc.classical_baseline_objective, 3)
  },
  {
    key: "composite_score",
    label: "Composite",
    tooltip: "Weighted blend of all metrics, scaled 0–10. Higher is better.",
    align: "right",
    numeric: true,
    format: (sc) => formatNumber(sc.composite_score, 2)
  }
];

type Props = {
  scorecards: Scorecard[];
  winnerAgent: string | null;
  runnerUpAgent: string | null;
};

export function ScorecardTable({ scorecards, winnerAgent, runnerUpAgent }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("composite_score");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(() => {
    const list = [...scorecards];
    list.sort((a, b) => {
      const va = (a as Record<string, unknown>)[sortKey];
      const vb = (b as Record<string, unknown>)[sortKey];
      if (typeof va === "number" && typeof vb === "number") {
        return direction === "asc" ? va - vb : vb - va;
      }
      const sa = String(va ?? "");
      const sb = String(vb ?? "");
      return direction === "asc" ? sa.localeCompare(sb) : sb.localeCompare(sa);
    });
    return list;
  }, [direction, scorecards, sortKey]);

  if (scorecards.length === 0) return null;

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setDirection(key === "agent_name" ? "asc" : "desc");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Scorecard comparison</CardTitle>
        <CardDescription>
          Six deterministic metrics, blended into a composite score. Click any column header to sort.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <TooltipProvider>
          <div className="-mx-2 overflow-x-auto px-2">
            <Table>
              <TableHeader>
                <TableRow>
                  {COLUMNS.map((column, index) => {
                    const isSorted = sortKey === column.key;
                    const ariaSort = isSorted
                      ? direction === "asc"
                        ? "ascending"
                        : "descending"
                      : "none";
                    return (
                      <TableHead
                        key={column.key}
                        aria-sort={ariaSort}
                        className={cn(
                          "select-none",
                          column.align === "right" && "text-right",
                          index === 0 && "sticky left-0 z-10 bg-card"
                        )}
                      >
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              onClick={() => handleSort(column.key)}
                              aria-label={`Sort by ${column.label.toLowerCase()}`}
                              className={cn(
                                "flex w-full items-center gap-1 text-xs font-medium uppercase tracking-wider text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:rounded-sm",
                                column.align === "right" && "justify-end"
                              )}
                            >
                              {column.label}
                              {isSorted ? (
                                direction === "asc" ? (
                                  <ArrowUp className="h-3 w-3" aria-hidden />
                                ) : (
                                  <ArrowDown className="h-3 w-3" aria-hidden />
                                )
                              ) : null}
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-xs text-xs">
                            {column.tooltip}
                          </TooltipContent>
                        </Tooltip>
                      </TableHead>
                    );
                  })}
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map((scorecard) => {
                  const isWinner = winnerAgent === scorecard.agent_name;
                  const isRunnerUp = runnerUpAgent === scorecard.agent_name;
                  return (
                    <TableRow
                      key={scorecard.agent_name}
                      data-winner={isWinner ? "true" : undefined}
                      className={cn(
                        isWinner && "bg-success/10",
                        !isWinner && isRunnerUp && "bg-muted/40"
                      )}
                    >
                      {COLUMNS.map((column, index) => (
                        <TableCell
                          key={column.key}
                          className={cn(
                            column.align === "right" && "text-right font-mono tabular-nums",
                            index === 0 &&
                              cn(
                                "sticky left-0 z-10",
                                isWinner ? "bg-success/10" : isRunnerUp ? "bg-muted/40" : "bg-card"
                              )
                          )}
                        >
                          {column.format(scorecard)}
                          {column.key === "agent_name" && isWinner ? (
                            <span className="ml-2 rounded-full bg-success px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-success-foreground">
                              Winner
                            </span>
                          ) : null}
                          {column.key === "agent_name" && !isWinner && isRunnerUp ? (
                            <span className="ml-2 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                              Runner-up
                            </span>
                          ) : null}
                        </TableCell>
                      ))}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </TooltipProvider>
      </CardContent>
    </Card>
  );
}

function formatRatio(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(0)}%`;
}

function formatNumber(value: number, digits: number): string {
  if (!Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function formatLargeNumber(value: number): string {
  if (!Number.isFinite(value)) return "∞";
  if (Math.abs(value) >= 1000) return value.toExponential(2);
  return value.toFixed(2);
}
