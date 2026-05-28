"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { SHORTCUTS } from "@/lib/keyboard-shortcuts";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function ShortcutsDialog({ open, onOpenChange }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>
            Quick access to the most common actions. Shortcuts are inactive while typing in
            a text field or the code editor.
          </DialogDescription>
        </DialogHeader>
        <ul className="divide-y rounded-md border">
          {SHORTCUTS.map((shortcut) => (
            <li
              key={shortcut.id}
              className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
            >
              <div>
                <p className="font-medium">{shortcut.label}</p>
                <p className="text-xs text-muted-foreground">{shortcut.description}</p>
              </div>
              <kbd className="rounded-md border bg-muted px-2 py-0.5 font-mono text-sm shadow-sm">
                {shortcut.chip}
              </kbd>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
