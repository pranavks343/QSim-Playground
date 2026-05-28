import { KeyboardShortcutsProvider } from "@/components/shared/keyboard-shortcuts-provider";
import { Nav } from "@/components/shared/nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
      <KeyboardShortcutsProvider />
    </div>
  );
}
