"use client";

import { LogOut, Menu, UserCircle, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { ThemeToggle } from "@/components/shared/theme-toggle";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const links = [
  { href: "#how-it-works", label: "How it works" },
  { href: "https://github.com/pranavks343/QSim-Playground", label: "GitHub" },
  { href: "#docs", label: "Docs" }
];

type NavClientProps = {
  isAuthenticated: boolean;
  email: string | null;
};

export function NavClient({ isAuthenticated, email }: NavClientProps) {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b bg-background/82 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-normal">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-sm text-primary-foreground">
            Q
          </span>
          <span>QSim Playground</span>
        </Link>
        <nav aria-label="Primary" className="hidden items-center gap-6 md:flex">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              {link.label}
            </a>
          ))}
        </nav>
        <div className="hidden items-center gap-2 md:flex">
          <ThemeToggle />
          {isAuthenticated ? <AuthenticatedActions email={email} /> : <GuestActions />}
        </div>
        <div className="flex items-center gap-2 md:hidden">
          <ThemeToggle />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
        </div>
      </div>
      <div
        className={cn(
          "border-t bg-background px-4 py-4 md:hidden",
          open ? "block" : "hidden"
        )}
      >
        <nav aria-label="Mobile primary" className="mx-auto grid max-w-6xl gap-3">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={() => setOpen(false)}
            >
              {link.label}
            </a>
          ))}
          <div className="grid gap-2 pt-2">
            {isAuthenticated ? (
              <>
                <Button asChild>
                  <Link href="/dashboard">Dashboard</Link>
                </Button>
                <LogoutButton />
              </>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <Button asChild variant="outline">
                  <Link href="/login">Sign in</Link>
                </Button>
                <Button asChild>
                  <Link href="/signup">Try free</Link>
                </Button>
              </div>
            )}
          </div>
        </nav>
      </div>
    </header>
  );
}

function GuestActions() {
  return (
    <>
      <Button asChild variant="ghost">
        <Link href="/login">Sign in</Link>
      </Button>
      <Button asChild>
        <Link href="/signup">Try free</Link>
      </Button>
    </>
  );
}

function AuthenticatedActions({ email }: { email: string | null }) {
  return (
    <>
      <Button asChild variant="ghost">
        <Link href="/dashboard">Dashboard</Link>
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="icon" variant="outline" aria-label="Open account menu">
            <UserCircle className="h-5 w-5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <div className="px-2 py-1.5 text-xs text-muted-foreground">{email ?? "Signed in"}</div>
          <DropdownMenuItem asChild>
            <Link href="/dashboard">Dashboard</Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <LogoutButton variant="menu" />
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
}

function LogoutButton({ variant = "button" }: { variant?: "button" | "menu" }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const logout = () => {
    startTransition(async () => {
      try {
        await createClient().auth.signOut();
        toast.success("Signed out");
        router.push("/");
        router.refresh();
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Could not sign out");
      }
    });
  };

  if (variant === "menu") {
    return (
      <button type="button" className="flex w-full items-center gap-2" onClick={logout}>
        <LogOut className="h-4 w-4" />
        Sign out
      </button>
    );
  }

  return (
    <Button type="button" variant="outline" onClick={logout} disabled={isPending}>
      <LogOut className="h-4 w-4" />
      Sign out
    </Button>
  );
}
