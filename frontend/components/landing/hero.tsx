import Link from "next/link";
import { ArrowRight, Play } from "lucide-react";

import { Button } from "@/components/ui/button";

export function Hero() {
  return (
    <section className="bg-background">
      <div className="mx-auto grid min-h-[72vh] max-w-6xl gap-10 px-4 py-16 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
        <div className="max-w-2xl">
          <p className="mb-4 text-sm font-medium text-accent">Multi-agent QUBO formulation</p>
          <h1 className="text-4xl font-semibold tracking-normal sm:text-5xl">
            QSim Playground
          </h1>
          <p className="mt-5 max-w-xl text-lg leading-8 text-muted-foreground">
            Turn optimization problems into competing quantum formulations, score them against a
            classical baseline, and export a reproducible Qiskit notebook.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/signup">
                Start a run <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/login">Open dashboard</Link>
            </Button>
          </div>
        </div>
        <div className="rounded-lg border bg-card p-3 shadow-sm">
          <div className="flex aspect-video items-center justify-center rounded-md bg-muted text-muted-foreground">
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-primary-foreground">
                <Play className="h-5 w-5" />
              </span>
              <span className="text-sm font-medium">Demo video placeholder</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
