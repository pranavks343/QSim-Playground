"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from "@/components/ui/table";
import type { ClassicalResult, SimulationResult } from "@/lib/types";
import { cn } from "@/lib/utils";

const QUALITY_THRESHOLD = 80;

type Props = {
  classical: ClassicalResult | null;
  simulation: SimulationResult | null;
};

export function BenchmarkPanel({ classical, simulation }: Props) {
  const quality = simulation?.quality_vs_classical ?? null;
  const honesty = useMemo(() => {
    if (quality === null || classical === null) return null;
    if (quality >= QUALITY_THRESHOLD) {
      return {
        kind: "success" as const,
        title: "Quantum matches the classical baseline.",
        body: `Simulator solution is at ${quality.toFixed(1)}% of the classical optimum — competitive on this instance.`
      };
    }
    return {
      kind: "warning" as const,
      title: "Classical wins on this instance.",
      body:
        `Simulator solution is at ${quality.toFixed(1)}% of the classical optimum. ` +
        "Quantum advantage isn't expected for problems this small or dense — that's the honest answer."
    };
  }, [classical, quality]);

  const chartData = useMemo(() => {
    if (!simulation) return [];
    return simulation.top_5_bitstrings.map(([bitstring, shots, objective]) => ({
      bitstring,
      shots,
      objective
    }));
  }, [simulation]);

  if (classical === null && simulation === null) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Benchmarks</CardTitle>
        <CardDescription>
          Classical vs. quantum simulator vs. hardware. We report what the baseline did and how the
          quantum candidate compared — no cherry-picking.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {honesty ? (
          <Alert
            className={cn(
              honesty.kind === "success"
                ? "border-success/40 bg-success/10 text-foreground"
                : "border-warning/50 bg-warning/10 text-foreground"
            )}
          >
            <AlertTitle>{honesty.title}</AlertTitle>
            <AlertDescription>{honesty.body}</AlertDescription>
          </Alert>
        ) : null}

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Method</TableHead>
                <TableHead className="text-right">Runtime</TableHead>
                <TableHead className="text-right">Best objective</TableHead>
                <TableHead className="text-right">Quality vs. classical</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>
                  <Badge variant="secondary">Classical · SA</Badge>
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {classical ? formatMs(classical.runtime_ms) : "—"}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {classical ? classical.best_objective.toFixed(4) : "—"}
                </TableCell>
                <TableCell className="text-right">—</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>
                  <Badge>Quantum · Aer simulator</Badge>
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {simulation ? formatMs(simulation.runtime_ms) : "—"}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {simulation ? simulation.best_objective.toFixed(4) : "—"}
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right font-mono tabular-nums",
                    quality !== null && quality < QUALITY_THRESHOLD && "text-warning",
                    quality !== null && quality >= QUALITY_THRESHOLD && "text-success"
                  )}
                >
                  {quality !== null ? `${quality.toFixed(1)}%` : "—"}
                </TableCell>
              </TableRow>
              <TableRow className="text-muted-foreground">
                <TableCell>
                  <Badge variant="outline">Hardware</Badge>{" "}
                  <span className="text-xs">Coming Day 6+</span>
                </TableCell>
                <TableCell className="text-right">—</TableCell>
                <TableCell className="text-right">—</TableCell>
                <TableCell className="text-right">—</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>

        {simulation && chartData.length > 0 ? (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Top-5 bitstrings (simulator)</h3>
            <p className="text-xs text-muted-foreground">
              How shots distributed across the top candidates. Lower-objective bitstrings are
              shown in the table label.
            </p>
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 16, bottom: 24, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.4} />
                  <XAxis
                    dataKey="bitstring"
                    tick={{ fontSize: 11, fontFamily: "monospace" }}
                    interval={0}
                    angle={-15}
                    dy={8}
                  />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip
                    cursor={{ fillOpacity: 0.1 }}
                    formatter={(value) => [`${String(value)} shots`, "Count"]}
                    labelFormatter={(label) => `Bitstring ${String(label)}`}
                  />
                  <Bar dataKey="shots" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : null}

        {simulation ? (
          <p className="text-xs text-muted-foreground">
            Total shots: {simulation.total_shots}. Best bitstring:{" "}
            <span className="font-mono">{simulation.best_bitstring}</span>.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function formatMs(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value < 1) return `${(value * 1000).toFixed(1)} µs`;
  if (value < 1000) return `${value.toFixed(1)} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}
