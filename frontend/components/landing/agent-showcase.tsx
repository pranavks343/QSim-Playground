import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

const agents = [
  { name: "Penalty", score: 8.6, note: "compact, constraint weighted" },
  { name: "Slack", score: 7.9, note: "exact inequalities, more qubits" },
  { name: "Graph", score: 8.2, note: "sparse max-cut structure" },
  { name: "Decomp", score: 7.1, note: "monolithic for small n" },
  { name: "Domain", score: 9.0, note: "Markowitz formulation" }
];

export function AgentShowcase() {
  return (
    <section className="bg-background">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div>
          <p className="text-sm font-medium text-accent">Killer feature</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-normal">Watch the agents think.</h2>
          <p className="mt-4 text-base leading-7 text-muted-foreground">
            The agents disagree because they use different formulation strategies, not because we
            changed a temperature setting. You see the formulation, scorecard, and tradeoff behind
            every recommendation.
          </p>
        </div>
        <div className="rounded-lg border bg-card p-4 shadow-sm" aria-label="Static preview of agent trace cards">
          <div className="grid gap-3">
            {agents.map((agent, index) => (
              <div key={agent.name} className="rounded-md border bg-background p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium">{agent.name} Agent</h3>
                      {index === 4 ? <Badge variant="success">winner</Badge> : null}
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">{agent.note}</p>
                  </div>
                  <span className="font-mono text-sm">{agent.score.toFixed(1)}</span>
                </div>
                <Progress value={agent.score * 10} className="mt-3" />
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            Preview data only. Live runs stream events from Supabase Realtime in later blocks.
          </p>
        </div>
      </div>
    </section>
  );
}
