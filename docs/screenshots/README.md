# Screenshots

This directory holds the visual assets referenced from the project
README. Capture these during the Day 4 integration test
(`docs/INTEGRATION_TEST.md`) and drop them in here as PNGs with the
exact filenames below so the README links resolve.

## Required captures

| Filename | What to capture | Notes |
|---|---|---|
| `agent-trace-live.png` | A run on `/runs/<id>` mid-flight — at least two agent cards still in the `Running` state with the animated pulse, others `Done`. The stepper should have the `Critic` step in `active`. | Light mode. Hide the dock / dev tools. |
| `agent-trace-done.png` | The same screen with `status=done`. Scorecard table sorted by composite desc, critic verdict panel visible, benchmark panel showing the **green honesty banner** (or amber if your run fell below 80%). | Light mode. |
| `agent-trace-dark.png` | The done view above in **dark mode**. | Toggle via the theme switcher in the nav. |
| `share-page.png` | A `/share/<id>` page opened in an incognito window logged-out. The "Read-only" badge must be visible top-right. | Cmd-Shift-T (or equivalent) to ensure no auth cookies bleed in. |
| `dashboard.png` | `/dashboard` with at least two recent runs in the grid and the quota bar populated. | Light mode. |
| `new-run.png` | `/new` with the Code tab active, the Monaco editor populated, qubit estimate ≥18 to show the warning banner. | Light mode. |

## Tips

- 1440×900 viewport produces a good aspect ratio for the trace screen
  and fits inline in GitHub READMEs without scaling artefacts.
- Use Cmd-Shift-4 (macOS) for area captures or Chrome DevTools'
  "Capture full size screenshot" command via Cmd-Shift-P.
- Compress before committing (`pngquant --quality=70-90 *.png` or the
  online ImageOptim equivalent) — these can easily exceed a megabyte
  each and bloat clones.
- If a capture needs to be redone, replace the file in place; the
  README links use stable filenames so no doc edits are required.
