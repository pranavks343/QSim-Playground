import { Badge } from "@/components/ui/badge";
import type { Run } from "@/lib/types";
import { cn } from "@/lib/utils";

const styles: Record<Run["status"], string> = {
  queued: "bg-muted text-muted-foreground",
  running: "animate-pulse bg-primary text-primary-foreground",
  done: "bg-success text-success-foreground",
  failed: "bg-destructive text-destructive-foreground",
  timeout: "bg-warning text-warning-foreground",
  cancelled: "bg-muted text-muted-foreground"
};

export function StatusBadge({ status }: { status: Run["status"] }) {
  return <Badge className={cn("capitalize", styles[status])}>{status}</Badge>;
}
