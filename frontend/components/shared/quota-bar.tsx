"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { getProfile } from "@/lib/api";
import type { Profile } from "@/lib/types";

export function QuotaBar() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load quota"));
  }, []);

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }
  if (!profile) {
    return <Skeleton className="h-16 w-full" />;
  }

  const used = profile.monthly_runs_used;
  const limit = profile.monthly_runs_limit;
  const percent = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const tone = percent >= 100 ? "text-destructive" : percent >= 80 ? "text-warning" : "text-muted-foreground";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">
            {used} / {limit} runs this month
          </p>
          <p className={`text-xs ${tone}`}>
            Resets {profile.quota_resets_at ? new Date(profile.quota_resets_at).toLocaleDateString() : "monthly"}
          </p>
        </div>
        <Badge variant="outline">{profile.tier}</Badge>
      </div>
      <Progress value={percent} />
    </div>
  );
}
