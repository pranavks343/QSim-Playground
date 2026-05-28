import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

export default function DashboardPage() {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Card className="md:col-span-2">
        <CardHeader>
          <CardTitle>Runs</CardTitle>
          <CardDescription>Recent pipeline runs will appear here after auth wiring.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border p-6 text-sm text-muted-foreground">No runs loaded yet.</div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Quota</CardTitle>
          <CardDescription>Free tier monthly run budget</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Progress value={0} />
          <p className="text-sm text-muted-foreground">Connect profile API in Block B.</p>
        </CardContent>
      </Card>
    </div>
  );
}
