import { strict as assert } from "node:assert";
import test from "node:test";

import { matchShortcut, SHORTCUTS } from "../lib/keyboard-shortcuts.ts";

type FakeEvent = {
  key: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  target?: EventTarget | null;
  defaultPrevented?: boolean;
};

function event(overrides: Partial<FakeEvent>): FakeEvent {
  return {
    key: "",
    shiftKey: false,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    target: null,
    defaultPrevented: false,
    ...overrides
  };
}

test("plain 'n' triggers the new-run shortcut", () => {
  const match = matchShortcut(event({ key: "n" }));
  assert.notEqual(match, null);
  assert.equal(match?.id, "new_run");
});

test("uppercase 'N' still triggers the new-run shortcut", () => {
  const match = matchShortcut(event({ key: "N" }));
  assert.equal(match?.id, "new_run");
});

test("shift+? triggers the shortcuts help dialog", () => {
  const match = matchShortcut(event({ key: "?", shiftKey: true }));
  assert.equal(match?.id, "shortcuts_help");
});

test("modifier keys (ctrl/meta/alt) suppress shortcut matching", () => {
  assert.equal(matchShortcut(event({ key: "n", ctrlKey: true })), null);
  assert.equal(matchShortcut(event({ key: "n", metaKey: true })), null);
  assert.equal(matchShortcut(event({ key: "n", altKey: true })), null);
});

test("preventDefault skips matching to respect upstream cancellation", () => {
  assert.equal(matchShortcut(event({ key: "n", defaultPrevented: true })), null);
});

test("input/textarea/contenteditable targets suppress shortcuts", () => {
  // We can't easily construct real HTMLElement in Node, so we mimic the
  // attribute shape via duck-typed objects guarded behind a global.
  type Mock = { isContentEditable: boolean; tagName: string; getAttribute: () => null };
  const previousHTMLElement = (globalThis as { HTMLElement?: unknown }).HTMLElement;
  class FakeElement {
    isContentEditable = false;
    tagName: string;
    getAttribute(): null {
      return null;
    }
    constructor(tagName: string) {
      this.tagName = tagName;
    }
  }
  (globalThis as { HTMLElement?: unknown }).HTMLElement = FakeElement;
  try {
    const input: Mock = new FakeElement("INPUT") as unknown as Mock;
    const textarea: Mock = new FakeElement("TEXTAREA") as unknown as Mock;
    assert.equal(matchShortcut(event({ key: "n", target: input as unknown as EventTarget })), null);
    assert.equal(
      matchShortcut(event({ key: "n", target: textarea as unknown as EventTarget })),
      null
    );
    const editable = new FakeElement("DIV") as unknown as Mock;
    editable.isContentEditable = true;
    assert.equal(
      matchShortcut(event({ key: "n", target: editable as unknown as EventTarget })),
      null
    );
  } finally {
    if (previousHTMLElement === undefined) {
      delete (globalThis as { HTMLElement?: unknown }).HTMLElement;
    } else {
      (globalThis as { HTMLElement?: unknown }).HTMLElement = previousHTMLElement;
    }
  }
});

test("every registered shortcut survives the round-trip", () => {
  for (const shortcut of SHORTCUTS) {
    const match = matchShortcut(
      event({ key: shortcut.key, shiftKey: shortcut.shift })
    );
    assert.equal(match?.id, shortcut.id);
  }
});
