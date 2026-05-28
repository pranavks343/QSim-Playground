import Link from "next/link";

import { RecentRuns } from "@/components/runs/recent-runs";
import { QuotaBar } from "@/components/shared/quota-bar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function DashboardPage() {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Card className="md:col-span-2">
        <CardHeader className="flex-row items-center justify-between gap-4 space-y-0">
          <div>
            <CardTitle>Recent runs</CardTitle>
            <CardDescription>Latest QUBO formulation pipelines.</CardDescription>
          </div>
          <Button asChild>
            <Link href="/new">Start a new run</Link>
          </Button>
        </CardHeader>
        <CardContent>
          <RecentRuns />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Quota</CardTitle>
          <CardDescription>Free tier monthly run budget</CardDescription>
        </CardHeader>
        <CardContent>
          <QuotaBar />
        </CardContent>
      </Card>
    </div>
  );
}
