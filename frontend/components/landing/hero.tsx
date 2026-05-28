import { ArrowRight, Github, Play } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

export function Hero() {
  return (
    <section className="relative isolate overflow-hidden bg-background">
      <CircuitMotif />
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl gap-10 px-4 py-16 lg:grid-cols-[1.02fr_0.98fr] lg:items-center lg:py-20">
        <div className="max-w-2xl">
          <p className="mb-4 text-sm font-medium text-accent">Quantum optimization for production-minded teams</p>
          <h1 className="text-4xl font-semibold leading-tight tracking-normal text-foreground sm:text-5xl lg:text-6xl">
            Quantum optimization for ML engineers.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-muted-foreground">
            Drop in your NumPy optimization problem. Five specialized agents formulate competing
            QUBOs, benchmark them honestly against classical solvers, and hand you reproducible
            Qiskit code in minutes, not weeks.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button asChild size="lg">
              <Link href="/signup">
                Try the free demo <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="https://github.com/pranavks343/QSim-Playground">
                <Github className="h-4 w-4" /> View on GitHub
              </Link>
            </Button>
          </div>
        </div>
        <div className="rounded-lg border bg-card p-3 shadow-sm">
          <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-md bg-muted">
            <div className="absolute inset-0 opacity-60 [background-image:linear-gradient(to_right,hsl(var(--border))_1px,transparent_1px),linear-gradient(to_bottom,hsl(var(--border))_1px,transparent_1px)] [background-size:36px_36px]" />
            <div className="relative flex items-center gap-4 rounded-lg border bg-background/90 px-5 py-4 shadow-sm">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground">
                <Play className="h-5 w-5 fill-current" aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-medium">Demo video placeholder</p>
                <p className="text-xs text-muted-foreground">Loom embed swaps in on Day 5</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function CircuitMotif() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
      <div className="absolute left-1/2 top-10 h-[34rem] w-[34rem] -translate-x-1/2 rounded-full border border-border/70" />
      <div className="absolute right-12 top-24 h-px w-64 bg-border" />
      <div className="absolute right-20 top-24 h-24 w-px bg-border" />
      <div className="absolute right-[4.5rem] top-[11.5rem] h-3 w-3 rounded-full border border-accent bg-background" />
      <div className="absolute left-10 bottom-24 h-px w-52 bg-border" />
      <div className="absolute left-10 bottom-24 h-20 w-px bg-border" />
      <div className="absolute left-[3.9rem] bottom-[11.1rem] h-3 w-3 rounded-full border border-primary bg-background" />
    </div>
  );
}
