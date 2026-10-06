# NotebookLM generation is split into Submit and Collect stages

NotebookLM builds the Slide Deck on Google's side, so holding a browser open for the whole wait wastes capacity and cannot scale to about 70 users on one account. We decided that Submit (drive the browser, choose Generate now, confirm generation started) runs with a configurable number of browser contexts (the MVP uses one Google account and one context, since NotebookLM runs one generation at a time per account; a pool of accounts is a later step), and Collect (poll, download the deck) runs separately. The notebook URL is saved in the Job document as soon as it exists, so a crashed or restarted worker collects the existing deck and does not create a second notebook or spend more of the account's limited free-tier quota.

## Consequences

- Browser concurrency is capped by configuration (`NOTEBOOKLM_BROWSER_CONCURRENCY`, MVP: 1), not by the number of users. Raising it only makes sense with more than one account. Worker concurrency (`JOB_WORKER_CONCURRENCY`) is separate: extra workers let one Job narrate and compose while another waits on NotebookLM.
- Collect holds its browser while it waits for the deck, rather than polling and re-queueing: simpler, and with one account only one deck generates at a time anyway. Polling would free the browser for other Jobs' Submit once there are several accounts.
- A finished notebook is deleted after a verified download so a free account's notebook limit is not reached. Notebooks of Jobs that never produce a deck are not cleaned up.
- The file-based `notebooklm_job.json` resume state is replaced by fields on the Job document.

## Free-tier limits this design assumes

These figures were gathered by the team, not measured on our account (see issue #13), and they conflict in places; treat them as working estimates until measured.

- **Budget.** A free account shares a metered usage budget that refreshes on a rolling window of about 5 hours, not at a fixed time of day. Heavy features such as Slide Decks use a lot of it: roughly 10 to 15 generations per window. Taken at face value that is about 48 to 72 decks a day at best, so about 70 users a day on one free account would sit at the ceiling, and a burst of requests would wait hours for the next refresh.
- **Deck size.** A deck is capped at about 20 slides. We ask for 8 to 16 (`MIN_SLIDES`, `MAX_SLIDES`), which is under the cap and keeps each generation cheap.
- **Notebooks.** An account holds up to 100 notebooks, with up to 50 sources each. Each Job creates a notebook, which is why a finished one is deleted.

What follows for the design:

- The quota comes back on a rolling window, so `NOTEBOOKLM_QUOTA_RESET_UTC` (a fixed daily time) stays empty and parked Jobs are retried by probing (`NOTEBOOKLM_QUOTA_PROBE_MINUTES`).
- One free account is enough only if requests are spread across the day. If many users generate at once, the queue only moves the waiting around; a paid plan or a pool of accounts is what adds capacity. That decision is deferred until real usage and the measured limits are known.
- The wording NotebookLM shows when the budget runs out is still unknown, so quota detection (`NOTEBOOKLM_QUOTA_MARKERS`) is off until it is captured.
