import { Binary, BrainCircuit, FileCode2 } from "lucide-react";

const steps = [
  {
    icon: Binary,
    title: "Paste or pick",
    description: "Start from NumPy code, a math sketch, or a known template.",
    graphic: "x.T @ Q @ x"
  },
  {
    icon: BrainCircuit,
    title: "Watch agents compete",
    description: "Penalty, slack, graph, decomposition, and domain agents produce distinct QUBOs.",
    graphic: "5 strategies"
  },
  {
    icon: FileCode2,
    title: "Export the evidence",
    description: "Review benchmarks, verdicts, circuits, and reproducible Qiskit code.",
    graphic: "QAOA + SA"
  }
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="border-t bg-muted/35">
      <div className="mx-auto max-w-6xl px-4 py-16">
        <div className="max-w-2xl">
          <p className="text-sm font-medium text-accent">How it works</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-normal">From optimization idea to runnable quantum code.</h2>
        </div>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {steps.map((step, index) => (
            <article key={step.title} className="rounded-lg border bg-card p-5">
              <div className="flex items-center justify-between gap-4">
                <span className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <step.icon className="h-5 w-5" aria-hidden="true" />
                </span>
                <span className="text-sm text-muted-foreground">0{index + 1}</span>
              </div>
              <h3 className="mt-5 text-lg font-semibold">{step.title}</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{step.description}</p>
              <div className="mt-5 rounded-md border bg-muted/50 px-3 py-2 font-mono text-xs text-muted-foreground">
                {step.graphic}
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
