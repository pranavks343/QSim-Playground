"use client";

import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";

import type { SharedRun } from "@/lib/types";

const MARGIN = 14;
const QUALITY_THRESHOLD = 80;

export function buildRunPdf(run: SharedRun, downloadedAt: Date = new Date()): jsPDF {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const pageWidth = doc.internal.pageSize.getWidth();
  const contentWidth = pageWidth - MARGIN * 2;
  let cursorY = MARGIN;

  // Title block
  doc.setFont("helvetica", "bold");
  doc.setFontSize(18);
  doc.text("QSim Playground · Run Report", MARGIN, cursorY + 6);
  cursorY += 10;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(11);
  const subtitle = [
    run.template ?? run.problem_ir.name,
    `Generated ${downloadedAt.toLocaleString()}`,
    `Run id: ${run.id}`
  ].join("  ·  ");
  cursorY = writeWrappedText(doc, subtitle, MARGIN, cursorY + 6, contentWidth, 5);

  cursorY = sectionTitle(doc, "Problem summary", cursorY + 4);
  const problemSummary = [
    `Name: ${run.problem_ir.name}`,
    run.problem_ir.description ? `Description: ${run.problem_ir.description}` : null,
    `Variables: ${run.problem_ir.variables.length}`,
    `Constraints: ${run.problem_ir.constraints?.length ?? 0}`,
    `Objective: ${run.problem_ir.objective.sense}`
  ]
    .filter((line): line is string => line !== null)
    .join("\n");
  cursorY = writeWrappedText(doc, problemSummary, MARGIN, cursorY, contentWidth, 5);

  cursorY = sectionTitle(doc, "Five competing formulations", cursorY + 4);
  const scorecardRows = scorecardRowsFor(run);
  if (scorecardRows.length > 0) {
    autoTable(doc, {
      startY: cursorY,
      head: [
        [
          "Agent",
          "Qubits",
          "Sparsity",
          "Condition",
          "Penalty sens.",
          "Classical obj.",
          "Composite"
        ]
      ],
      body: scorecardRows,
      headStyles: { fillColor: [34, 34, 96], textColor: 255 },
      bodyStyles: { fontSize: 9 },
      theme: "striped",
      margin: { left: MARGIN, right: MARGIN }
    });
    const finalY = (doc as unknown as { lastAutoTable?: { finalY: number } }).lastAutoTable
      ?.finalY;
    cursorY = finalY ? finalY + 4 : cursorY + 30;
  } else {
    cursorY = writeWrappedText(
      doc,
      "Scorecards are not yet populated for this run.",
      MARGIN,
      cursorY,
      contentWidth,
      5
    );
  }

  cursorY = sectionTitle(doc, "Critic verdict", cursorY + 4);
  if (run.critic_verdict) {
    const verdict = run.critic_verdict;
    const block = [
      `Winner: ${verdict.winner_agent}`,
      `Runner-up: ${verdict.runner_up_agent}`,
      `Confidence: ${verdict.confidence}`,
      `Rejected: ${verdict.rejected_agents.join(", ") || "—"}`
    ].join("\n");
    cursorY = writeWrappedText(doc, block, MARGIN, cursorY, contentWidth, 5);
    cursorY = writeWrappedText(
      doc,
      verdict.rationale,
      MARGIN,
      cursorY + 2,
      contentWidth,
      5,
      "italic"
    );
  } else {
    cursorY = writeWrappedText(
      doc,
      "Critic verdict is not available for this run.",
      MARGIN,
      cursorY,
      contentWidth,
      5
    );
  }

  cursorY = sectionTitle(doc, "Benchmarks", cursorY + 4);
  const benchmark = benchmarkRowsFor(run);
  autoTable(doc, {
    startY: cursorY,
    head: [["Method", "Runtime", "Best objective", "Quality vs classical"]],
    body: benchmark.rows,
    headStyles: { fillColor: [34, 96, 34], textColor: 255 },
    bodyStyles: { fontSize: 9 },
    theme: "striped",
    margin: { left: MARGIN, right: MARGIN }
  });
  const benchY = (doc as unknown as { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY;
  cursorY = benchY ? benchY + 4 : cursorY + 24;

  if (benchmark.honesty) {
    const isWin = benchmark.honesty.kind === "success";
    doc.setFillColor(isWin ? 220 : 252, isWin ? 240 : 232, isWin ? 220 : 207);
    doc.setDrawColor(isWin ? 100 : 197, isWin ? 170 : 130, isWin ? 100 : 36);
    doc.roundedRect(MARGIN, cursorY, contentWidth, 14, 2, 2, "FD");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    doc.setTextColor(40, 40, 40);
    doc.text(benchmark.honesty.title, MARGIN + 3, cursorY + 5);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9);
    const wrapped = doc.splitTextToSize(benchmark.honesty.body, contentWidth - 6);
    doc.text(wrapped, MARGIN + 3, cursorY + 10);
    cursorY += 18;
  }

  cursorY = sectionTitle(doc, "Methodology", cursorY + 4);
  cursorY = writeWrappedText(
    doc,
    "Five LangGraph-orchestrated specialist agents (penalty, slack, graph, " +
      "decomposition, domain) each formulate a competing QUBO. A deterministic " +
      "evaluator scores them on six metrics; a critic selects the winner and a " +
      "refiner polishes it. The winning QUBO is compiled to a QAOA ansatz via " +
      "Qiskit and run on the Qiskit Aer simulator, with a simulated-annealing " +
      "baseline as the classical honesty anchor.",
    MARGIN,
    cursorY,
    contentWidth,
    5
  );

  doc.setFont("helvetica", "italic");
  doc.setFontSize(9);
  doc.setTextColor(90, 90, 90);
  const footer = "Generated by QSim Playground · qaoa simulated on Qiskit Aer";
  const footerY = doc.internal.pageSize.getHeight() - 8;
  doc.text(footer, pageWidth - MARGIN, footerY, { align: "right" });

  return doc;
}

function sectionTitle(doc: jsPDF, label: string, y: number): number {
  doc.setFont("helvetica", "bold");
  doc.setFontSize(12);
  doc.setTextColor(20, 20, 20);
  doc.text(label, MARGIN, y);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(11);
  doc.setTextColor(40, 40, 40);
  return y + 5;
}

function writeWrappedText(
  doc: jsPDF,
  body: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
  style: "normal" | "italic" = "normal"
): number {
  doc.setFont("helvetica", style);
  doc.setFontSize(10);
  doc.setTextColor(40, 40, 40);
  const lines = doc.splitTextToSize(body, maxWidth);
  doc.text(lines, x, y);
  return y + lines.length * lineHeight;
}

function scorecardRowsFor(run: SharedRun): (string | number)[][] {
  const scorecards = run.scorecards ?? {};
  return Object.values(scorecards).map((sc) => [
    sc.agent_name,
    sc.qubit_count,
    `${(sc.sparsity * 100).toFixed(0)}%`,
    formatLargeNumber(sc.condition_number),
    `${(sc.penalty_sensitivity * 100).toFixed(0)}%`,
    sc.classical_baseline_objective.toFixed(3),
    sc.composite_score.toFixed(2)
  ]);
}

function benchmarkRowsFor(run: SharedRun): {
  rows: (string | number)[][];
  honesty: { kind: "success" | "warning"; title: string; body: string } | null;
} {
  const classical = run.classical_result;
  const sim = run.sim_result;
  const quality = sim?.quality_vs_classical ?? null;
  const rows: (string | number)[][] = [
    [
      "Classical · SA",
      classical ? `${classical.runtime_ms.toFixed(1)} ms` : "—",
      classical ? classical.best_objective.toFixed(4) : "—",
      "—"
    ],
    [
      "Quantum · Aer",
      sim ? `${sim.runtime_ms.toFixed(1)} ms` : "—",
      sim ? sim.best_objective.toFixed(4) : "—",
      quality !== null ? `${quality.toFixed(1)}%` : "—"
    ],
    ["Hardware (coming Day 6+)", "—", "—", "—"]
  ];

  if (quality === null || classical === undefined || classical === null) {
    return { rows, honesty: null };
  }
  if (quality >= QUALITY_THRESHOLD) {
    return {
      rows,
      honesty: {
        kind: "success",
        title: "Quantum matches the classical baseline.",
        body: `Simulator solution is at ${quality.toFixed(
          1
        )}% of the classical optimum — competitive on this instance.`
      }
    };
  }
  return {
    rows,
    honesty: {
      kind: "warning",
      title: "Classical wins on this instance.",
      body:
        `Simulator solution is at ${quality.toFixed(1)}% of the classical optimum. ` +
        "Quantum advantage isn't expected for problems this small or dense — that's the honest answer."
    }
  };
}

function formatLargeNumber(value: number): string {
  if (!Number.isFinite(value)) return "∞";
  if (Math.abs(value) >= 1000) return value.toExponential(2);
  return value.toFixed(2);
}
