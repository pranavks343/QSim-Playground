import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { RunDetailView } from "@/components/runs/run-detail-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchRunInitial, isError } from "@/lib/api-server";

export const dynamic = "force-dynamic";

type Props = {
  params: { id: string };
};

export default async function RunDetailPage({ params }: Props) {
  const result = await fetchRunInitial(params.id);
  if (isError(result)) {
    if (result.status === 401) {
      redirect(`/login?returnUrl=/runs/${params.id}`);
    }
    if (result.status === 404) {
      notFound();
    }
    return (
      <Card className="border-destructive/40 bg-destructive/5">
        <CardHeader>
          <CardTitle>We could not load this run</CardTitle>
          <CardDescription>
            The backend returned <span className="font-mono">{result.status}</span>.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">{result.message}</p>
          <Button asChild variant="outline">
            <Link href="/dashboard">Back to dashboard</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }
  return <RunDetailView initialRun={result.run} initialEvents={result.events} />;
}
