import Link from "next/link";

import { Badge } from "@/components/ui/badge";

export function Footer() {
  return (
    <footer className="border-t bg-background" id="docs">
      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-10 md:grid-cols-[1fr_auto] md:items-center">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <p className="font-semibold">QSim Playground</p>
            <Badge variant="outline">MIT licensed</Badge>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Built by{" "}
            <Link href="https://pranavks.co.in" className="text-foreground underline-offset-4 hover:underline">
              Pranav
            </Link>
            . Contact:{" "}
            <Link
              href="mailto:kondapisripranav@gmail.com"
              className="text-foreground underline-offset-4 hover:underline"
            >
              kondapisripranav@gmail.com
            </Link>
          </p>
        </div>
        <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
          <Link href="https://github.com/pranavks343/QSim-Playground" className="hover:text-foreground">
            GitHub
          </Link>
          <Link href="#how-it-works" className="hover:text-foreground">
            Docs
          </Link>
          <span>Copyright 2026</span>
        </div>
      </div>
    </footer>
  );
}
