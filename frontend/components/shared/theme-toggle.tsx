"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  // next-themes can't know the user's preference during SSR, so the
  // server renders one icon and the client may render another, causing
  // a hydration mismatch on the inner <svg>. Defer the icon swap until
  // after mount and render a stable, icon-shaped placeholder in the
  // meantime so layout does not shift.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const isDark = resolvedTheme === "dark";

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      aria-label="Toggle dark mode"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      suppressHydrationWarning
    >
      {mounted ? (
        isDark ? (
          <Sun className="h-4 w-4" aria-hidden />
        ) : (
          <Moon className="h-4 w-4" aria-hidden />
        )
      ) : (
        // Reserves exactly the same box the icon will occupy after mount.
        <span className="block h-4 w-4" aria-hidden />
      )}
    </Button>
  );
}
