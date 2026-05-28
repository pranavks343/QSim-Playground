import Link from "next/link";
import { notFound } from "next/navigation";

import { SharedRunView } from "@/components/runs/shared-run-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchSharedRun, isError } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: { id: string } }) {
  return {
    title: `Shared QSim run · ${params.id.slice(0, 8)}`,
    description:
      "Read-only snapshot of a multi-agent QUBO formulation run on QSim Playground.",
    robots: { index: false, follow: false }
  };
}

export default async function SharedRunPage({ params }: { params: { id: string } }) {
  const result = await fetchSharedRun(params.id);
  if (isError(result)) {
    if (result.status === 404) {
      notFound();
    }
    return (
      <div className="mx-auto max-w-3xl px-4 py-12">
        <Card className="border-destructive/40 bg-destructive/5">
          <CardHeader>
            <CardTitle>Cannot load shared run</CardTitle>
            <CardDescription>
              The backend returned <span className="font-mono">{result.status}</span>.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">{result.message}</p>
            <Button asChild variant="outline">
              <Link href="/">Back to QSim Playground</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }
  return <SharedRunView run={result} />;
}
