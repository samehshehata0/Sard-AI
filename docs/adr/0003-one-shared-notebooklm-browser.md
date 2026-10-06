# NotebookLM work runs in one long-lived browser, not one per job

Each Submit and Collect used to launch its own Chromium, load the saved login, do its work and close it. We now keep a single browser open and signed in for the life of the app (`BrowserHost`), and each operation opens a fresh tab in it. The session stays warm (cookies rotate in place), there are far fewer launches, and there is one place that owns the browser. Playwright's synchronous API belongs to the thread that started it, so the browser lives on one dedicated daemon thread and every operation is queued onto it.

## Consequences

- Browser work is serial, whatever `NOTEBOOKLM_BROWSER_CONCURRENCY` says. With one Google account NotebookLM generates one deck at a time anyway, so little is lost; running several browsers in parallel would need several accounts (each with its own host) and is a later step. Extra job workers still let other stages (narration, video) overlap with a deck being generated.
- A long Collect (waiting for a deck) holds the browser thread, so other jobs' Submit waits behind it, as it did under the old browser cap of 1.
- The browser is rebuilt when it must be: it died; the saved login changed on disk (`npm run auth` was run again, otherwise the old cookies would stay loaded); or it has been open for `NOTEBOOKLM_BROWSER_RECYCLE_HOURS` (12), so a Chromium open for days cannot leak memory forever. The app's own refresh of the login file is not treated as a new login.
- A tab is closed after every operation, even a failed one; evidence (screenshot, DOM) is captured before the tab closes.
- The browser is closed when the app shuts down. If it is busy with a long operation the app does not wait for it; the thread is a daemon, so shutdown is never held up for hours.
- `npm run canary` and the slide-image extraction still use their own short-lived browsers.
