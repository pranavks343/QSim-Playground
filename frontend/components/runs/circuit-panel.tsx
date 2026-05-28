"use client";

import { useState } from "react";
import SyntaxHighlighter from "react-syntax-highlighter";
// eslint-disable-next-line import/no-named-as-default-member
import { atomOneDark } from "react-syntax-highlighter/dist/esm/styles/hljs";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { CircuitData } from "@/lib/types";

export type CircuitPreview = Pick<CircuitData, "qubit_count" | "depth" | "gate_count"> &
  Partial<Pick<CircuitData, "reps" | "qiskit_qasm" | "circuit_image_svg">>;

type Props = {
  circuit: CircuitPreview | null;
};

export function CircuitPanel({ circuit }: Props) {
  const [showQasm, setShowQasm] = useState(false);

  if (circuit === null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>QAOA circuit</CardTitle>
          <CardDescription>Circuit metadata will appear after the run completes.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>QAOA circuit</CardTitle>
        <CardDescription>
          Synthesised QAOA ansatz from the refined QUBO. Lower depth and gate count are preferred.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Qubits" value={circuit.qubit_count} />
          <Stat label="Depth" value={circuit.depth} />
          <Stat label="Gates" value={circuit.gate_count} />
          <Stat label="Reps (p)" value={circuit.reps ?? "—"} />
        </div>

        {circuit.circuit_image_svg ? (
          <div
            className="overflow-x-auto rounded-md border bg-card p-3"
            dangerouslySetInnerHTML={{ __html: circuit.circuit_image_svg }}
          />
        ) : (
          <div className="space-y-2">
            {circuit.qiskit_qasm ? (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowQasm((value) => !value)}
                  aria-expanded={showQasm}
                >
                  {showQasm ? "Hide QASM" : "View QASM"}
                </Button>
                {showQasm ? (
                  <div className="overflow-x-auto rounded-md border text-xs">
                    <SyntaxHighlighter
                      language="qasm"
                      style={atomOneDark}
                      customStyle={{ margin: 0, padding: "0.75rem" }}
                      wrapLongLines
                    >
                      {circuit.qiskit_qasm}
                    </SyntaxHighlighter>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="text-xs text-muted-foreground">
                Full OpenQASM export arrives with the completed run snapshot.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-lg tabular-nums">{value}</div>
      <Badge variant="outline" className="mt-2 text-[10px]">
        {valueHint(label)}
      </Badge>
    </div>
  );
}

function valueHint(label: string): string {
  switch (label) {
    case "Qubits":
      return "Width";
    case "Depth":
      return "Latency proxy";
    case "Gates":
      return "Total ops";
    case "Reps (p)":
      return "QAOA layers";
    default:
      return "";
  }
}
