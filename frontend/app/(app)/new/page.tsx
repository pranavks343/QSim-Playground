import { NewRunPanel } from "@/components/runs/new-run-panel";

export default function NewRunPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-normal">New run</h1>
      <p className="mt-2 text-muted-foreground">Choose a template, paste NumPy, or build a small IR by hand.</p>
      <div className="mt-6">
        <NewRunPanel />
      </div>
    </div>
  );
}
