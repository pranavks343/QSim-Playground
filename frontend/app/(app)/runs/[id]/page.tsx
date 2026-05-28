import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function RunDetailPage({ params }: { params: { id: string } }) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-normal">Run {params.id}</h1>
        <Badge variant="secondary">Realtime shell</Badge>
      </div>
      <div className="grid gap-4 lg:grid-cols-5">
        {["Penalty", "Slack", "Graph", "Decomposition", "Domain"].map((agent) => (
          <Card key={agent}>
            <CardHeader>
              <CardTitle className="text-sm">{agent}</CardTitle>
            </CardHeader>
            <CardContent>
              <Skeleton className="h-20" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
