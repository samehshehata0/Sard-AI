# Sard AI

Sard AI turns an educational story request into slides, narration and video.

## Language

**Story**:
A user's request plus everything generated from it (slides, narration, video). Tracked by `story_id`.

**Slide Deck**:
The presentation NotebookLM produces from a Story's source text. The raw material for scenes.

**Slide Deck dialog**:
NotebookLM's customization form for a Slide Deck. Offers two actions: **Generate now** and **Generate later**.

**Generate now**:
Dialog action that starts Slide Deck creation immediately. The only action Sard uses.
_Avoid_: "Generate" (ambiguous — the label also matches Generate later)

**Generate later**:
Dialog action that defers Slide Deck creation. Sard must never pick it by accident; a deliberate user-facing "schedule for later" feature may use it or its own scheduler.

**Job**:
A queued unit of work for one Story. Moves through Stages and survives restarts.

**Stage**:
One step of a Job (submit to NotebookLM, collect the deck, extract slides, narrate, compose video, upload). Each Stage is retried on its own and keeps its output.

**Submit / Collect**:
The two halves of the NotebookLM Stage. Submit drives the browser to start generation; Collect waits for the Slide Deck and downloads it.

**Needs login**:
Job state when the NotebookLM session has expired. Jobs wait here, not failed, until a person logs in again.

**Quota exhausted**:
Job state when NotebookLM refuses new Slide Decks because the account's usage budget is used up. Jobs wait here until the budget comes back.

**Usage budget**:
The metered allowance of a NotebookLM account that Slide Decks draw on. On a free account it refreshes on a rolling window of about 5 hours (not at a fixed time of day) and covers roughly 10 to 15 decks per window. These figures are reported, not yet measured.

**Slide cap**:
The most slides NotebookLM puts in one deck, about 20. Sard asks for 8 to 16.

**Dead letter**:
Final state of a Job that used all its retries. Kept with its error and evidence so an admin can requeue it.

**Active Job**:
A Job that is queued or running. A user may have at most two at a time (a soft limit, until real accounts replace the anonymous cookie).

**Duplicate request**:
A story request identical to one that is still an Active Job for the same user. It is not queued twice; the user is shown the existing Story.

**Cancelled**:
Final state of a Job its user cancelled while it was still waiting. A Job a worker has started cannot be cancelled.

**Scheduled generation**:
A possible future feature: the user chooses when a Story is generated. Not built.
