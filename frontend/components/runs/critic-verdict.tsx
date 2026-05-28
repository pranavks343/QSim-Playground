"use client";

import { Quote } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { CriticVerdict } from "@/lib/types";
import { cn } from "@/lib/utils";

type Props = {
  verdict: CriticVerdict | null;
};

const CONFIDENCE_STYLES: Record<CriticVerdict["confidence"], string> = {
  high: "bg-success text-success-foreground",
  medium: "bg-warning text-warning-foreground",
  low: "bg-muted text-muted-foreground"
};

const CONFIDENCE_LABEL: Record<CriticVerdict["confidence"], string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence"
};

export function CriticVerdictPanel({ verdict }: Props) {
  if (verdict === null) return null;
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle>Critic verdict</CardTitle>
            <CardDescription>
              The critic compares scorecards, picks a winner, and explains why.
            </CardDescription>
          </div>
          <Badge className={cn("uppercase tracking-wider", CONFIDENCE_STYLES[verdict.confidence])}>
            {CONFIDENCE_LABEL[verdict.confidence]}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <blockquote className="relative rounded-md border-l-4 border-primary bg-primary/5 p-4 text-sm leading-relaxed text-foreground">
          <Quote
            aria-hidden
            className="absolute -left-2 -top-2 h-5 w-5 rounded-full bg-primary p-1 text-primary-foreground"
          />
          {verdict.rationale}
        </blockquote>
        <div className="flex flex-wrap gap-2">
          <ChipGroup label="Winner" agents={[verdict.winner_agent]} variant="winner" />
          <ChipGroup label="Runner-up" agents={[verdict.runner_up_agent]} variant="runner" />
          <ChipGroup label="Rejected" agents={verdict.rejected_agents} variant="rejected" />
        </div>
      </CardContent>
    </Card>
  );
}

function ChipGroup({
  label,
  agents,
  variant
}: {
  label: string;
  agents: string[];
  variant: "winner" | "runner" | "rejected";
}) {
  if (agents.length === 0) return null;
  const chipClasses =
    variant === "winner"
      ? "bg-success text-success-foreground border-success"
      : variant === "runner"
        ? "bg-card text-foreground border-foreground/40"
        : "bg-muted text-muted-foreground border-border";
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs uppercase tracking-wider text-muted-foreground">{label}</span>
      <div className="flex flex-wrap gap-1">
        {agents.map((agent) => (
          <span
            key={agent}
            className={cn(
              "rounded-full border px-2 py-0.5 text-xs font-medium capitalize",
              chipClasses
            )}
          >
            {agent}
          </span>
        ))}
      </div>
    </div>
  );
}
