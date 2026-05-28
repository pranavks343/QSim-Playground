// Pure helpers for matching keyboard events to global shortcuts.

export type ShortcutId = "new_run" | "shortcuts_help";

export type ShortcutDefinition = {
  id: ShortcutId;
  /** A single, lowercase letter we want to match (case-insensitive). */
  key: string;
  /** Whether shift must be held to match (covers "?" → shift+/). */
  shift: boolean;
  label: string;
  description: string;
  /** Display chip text (the actual keystroke the user sees). */
  chip: string;
};

export const SHORTCUTS: ShortcutDefinition[] = [
  {
    id: "new_run",
    key: "n",
    shift: false,
    label: "Start a new run",
    description: "Opens the New run page from anywhere in the app.",
    chip: "n"
  },
  {
    id: "shortcuts_help",
    key: "?",
    shift: true,
    label: "Show keyboard shortcuts",
    description: "Opens this dialog.",
    chip: "?"
  }
];

/**
 * Match a keydown event against the registered shortcuts.
 *
 * Returns `null` when the event should be ignored, e.g. when the user is
 * typing into an input or any modifier other than the configured shift
 * state is held. We deliberately exclude ctrl/meta/alt so we never
 * collide with browser or OS shortcuts.
 */
export function matchShortcut(
  event: {
    key: string;
    shiftKey: boolean;
    ctrlKey: boolean;
    metaKey: boolean;
    altKey: boolean;
    target?: EventTarget | null;
    defaultPrevented?: boolean;
  },
  shortcuts: ShortcutDefinition[] = SHORTCUTS
): ShortcutDefinition | null {
  if (event.defaultPrevented) return null;
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  if (isInteractiveTarget(event.target)) return null;
  const key = event.key.toLowerCase();
  return (
    shortcuts.find((shortcut) => {
      const wantsShift = shortcut.shift === true;
      if (wantsShift !== event.shiftKey) return false;
      return shortcut.key.toLowerCase() === key;
    }) ?? null
  );
}

function isInteractiveTarget(target: EventTarget | null | undefined): boolean {
  if (target === null || target === undefined) return false;
  if (typeof HTMLElement === "undefined") return false;
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  // Inside Monaco the editor's content sits in a div with role=textbox.
  const role = target.getAttribute("role");
  if (role === "textbox" || role === "combobox" || role === "searchbox") {
    return true;
  }
  return false;
}
