import { strict as assert } from "node:assert";
import test from "node:test";

import { deriveExportControlsState, shareUrlFor } from "../lib/export-state.ts";

test("export controls hidden while run is queued", () => {
  const state = deriveExportControlsState({ status: "queued", shared: false });
  assert.equal(state.visible, false);
  assert.equal(state.shared, false);
  assert.equal(state.canUnshare, false);
});

test("export controls hidden while run is running", () => {
  const state = deriveExportControlsState({ status: "running", shared: false });
  assert.equal(state.visible, false);
});

test("export controls hidden when run failed", () => {
  const state = deriveExportControlsState({ status: "failed", shared: false });
  assert.equal(state.visible, false);
});

test("export controls hidden when run timed out", () => {
  const state = deriveExportControlsState({ status: "timeout", shared: false });
  assert.equal(state.visible, false);
});

test("export controls hidden when run cancelled", () => {
  const state = deriveExportControlsState({ status: "cancelled", shared: false });
  assert.equal(state.visible, false);
});

test("export controls visible once run is done", () => {
  const state = deriveExportControlsState({ status: "done", shared: false });
  assert.equal(state.visible, true);
  assert.equal(state.shared, false);
  assert.equal(state.canUnshare, false);
});

test("share toggle reflects shared=true and exposes canUnshare", () => {
  const state = deriveExportControlsState({ status: "done", shared: true });
  assert.equal(state.visible, true);
  assert.equal(state.shared, true);
  assert.equal(state.canUnshare, true);
});

test("share state transitions cleanly between shared=false and shared=true", () => {
  const initial = deriveExportControlsState({ status: "done", shared: false });
  assert.equal(initial.canUnshare, false);
  const toggled = deriveExportControlsState({ status: "done", shared: true });
  assert.equal(toggled.canUnshare, true);
  const detoggled = deriveExportControlsState({ status: "done", shared: false });
  assert.equal(detoggled.canUnshare, false);
});

test("shareUrlFor honours explicit origin and falls back to window.location.origin", () => {
  assert.equal(
    shareUrlFor("abcd-1234", "https://qsim.example.com"),
    "https://qsim.example.com/share/abcd-1234"
  );
  // Simulate browser context.
  const previousWindow = (globalThis as { window?: unknown }).window;
  (globalThis as { window?: unknown }).window = {
    location: { origin: "https://demo.invalid" }
  };
  try {
    assert.equal(shareUrlFor("run-99"), "https://demo.invalid/share/run-99");
  } finally {
    if (previousWindow === undefined) {
      delete (globalThis as { window?: unknown }).window;
    } else {
      (globalThis as { window?: unknown }).window = previousWindow;
    }
  }
});
