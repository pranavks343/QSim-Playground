"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ShortcutsDialog } from "@/components/shared/shortcuts-dialog";
import { matchShortcut } from "@/lib/keyboard-shortcuts";

/**
 * Mount-once provider that binds global keyboard shortcuts and renders the
 * "?" help dialog. Placed inside the authenticated layout so shortcuts only
 * fire for signed-in users.
 */
export function KeyboardShortcutsProvider() {
  const router = useRouter();
  const [helpOpen, setHelpOpen] = useState(false);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      const shortcut = matchShortcut(event);
      if (shortcut === null) return;
      event.preventDefault();
      if (shortcut.id === "new_run") {
        router.push("/new");
        return;
      }
      if (shortcut.id === "shortcuts_help") {
        setHelpOpen((open) => !open);
      }
    },
    [router]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleKeyDown]);

  return <ShortcutsDialog open={helpOpen} onOpenChange={setHelpOpen} />;
}
