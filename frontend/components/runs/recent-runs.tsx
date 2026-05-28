"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getRuns } from "@/lib/api";
import type { Run } from "@/lib/types";

export function RecentRuns() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getRuns(10)
      .then(setRuns)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load runs"));
  }, []);

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }
  if (!runs) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
      </div>
    );
  }
  if (runs.length === 0) {
    return (
      <div className="rounded-md border p-6 text-sm text-muted-foreground">
        No runs yet. <Button asChild variant="link"><Link href="/new">Start a new run</Link></Button>
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {runs.map((run) => (
        <Card key={run.id}>
          <CardContent className="flex items-center justify-between gap-4 p-4">
            <div>
              <p className="font-medium">{run.template ?? run.problem_ir.name}</p>
              <p className="text-sm text-muted-foreground">{relativeTime(run.created_at)}</p>
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge status={run.status} />
              <Button asChild variant="outline" size="sm">
                <Link href={`/runs/${run.id}`}>View</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function relativeTime(value: string) {
  const deltaSeconds = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (deltaSeconds < 60) return "just now";
  const minutes = Math.round(deltaSeconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
