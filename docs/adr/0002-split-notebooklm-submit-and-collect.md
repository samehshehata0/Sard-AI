# NotebookLM generation is split into Submit and Collect stages

NotebookLM builds the Slide Deck on Google's side, so holding a browser open for the whole wait wastes capacity and cannot scale to about 70 users on one account. We decided that Submit (drive the browser, choose Generate now, confirm generation started) runs with a configurable number of browser contexts (the MVP uses one Google account and one context, since NotebookLM runs one generation at a time per account; a pool of accounts is a later step), and Collect (poll, download the deck) runs separately. The notebook URL is saved in the Job document as soon as it exists, so a crashed or restarted worker collects the existing deck and does not create a second notebook or spend more of the account's limited free-tier quota.

## Consequences

- Browser concurrency is capped by configuration (MVP: 1), not by the number of users. Raising it only makes sense with more than one account.
- The file-based `notebooklm_job.json` resume state is replaced by fields on the Job document.
