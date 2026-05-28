import { AlertTriangle, BarChart3, FileCode2 } from "lucide-react";

const items = [
  {
    icon: BarChart3,
    title: "Classical baseline included",
    copy: "Every quantum result is compared against a deterministic classical run."
  },
  {
    icon: AlertTriangle,
    title: "Quantum losses are visible",
    copy: "If QAOA underperforms the heuristic, the UI flags it instead of hiding it."
  },
  {
    icon: FileCode2,
    title: "Reproducible exports",
    copy: "Notebook, script, and PDF exports preserve the formulation and benchmark context."
  }
];

export function HonestySection() {
  return (
    <section className="border-t bg-muted/40">
      <div className="mx-auto max-w-6xl px-4 py-14">
        <h2 className="text-2xl font-semibold tracking-normal">Benchmarks before claims</h2>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {items.map((item) => (
            <div key={item.title} className="rounded-lg border bg-card p-5">
              <item.icon className="h-5 w-5 text-accent" />
              <h3 className="mt-4 font-medium">{item.title}</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.copy}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
