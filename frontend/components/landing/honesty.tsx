import { CheckCircle2, Scale } from "lucide-react";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const rows = [
  {
    quantum: "Structured objectives with reusable sparsity or graph structure",
    classical: "Small dense matrices where exact brute force or SA is already cheap"
  },
  {
    quantum: "Problems where circuit exploration reveals near-optimal candidates fast",
    classical: "Well-conditioned convex-like relaxations with strong classical heuristics"
  },
  {
    quantum: "Larger search spaces where formulation quality matters more than solver polish",
    classical: "Tightly constrained toy problems with few feasible states"
  }
];

export function Honesty() {
  return (
    <section className="border-y bg-muted/35">
      <div className="mx-auto max-w-6xl px-4 py-16">
        <div className="grid gap-8 lg:grid-cols-[0.8fr_1.2fr] lg:items-start">
          <div>
            <div className="flex h-11 w-11 items-center justify-center rounded-md bg-warning text-warning-foreground">
              <Scale className="h-5 w-5" aria-hidden="true" />
            </div>
            <h2 className="mt-5 text-3xl font-semibold tracking-normal">We show you when quantum loses.</h2>
            <p className="mt-4 leading-7 text-muted-foreground">
              Most quantum demos overhype. QSim reports the classical baseline next to every
              quantum result, so you can make an honest engineering call before investing more
              time in a formulation.
            </p>
          </div>
          <div className="rounded-lg border bg-card p-2 shadow-sm">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Quantum tends to win when...</TableHead>
                  <TableHead>Classical wins when...</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.quantum}>
                    <TableCell>
                      <span className="flex gap-2">
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />
                        {row.quantum}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{row.classical}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>
    </section>
  );
}
