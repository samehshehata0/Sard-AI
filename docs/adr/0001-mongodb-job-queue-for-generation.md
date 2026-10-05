# Story generation runs through a MongoDB-backed job queue

Generation used to run inside one HTTP request to the Python backend that could stay open for up to two hours, with no retry, no limit on parallel browsers, and no recovery after a crash. We decided to enqueue each Story as a Job in a MongoDB collection, split into Stages that are retried independently, and claimed by Python workers using a lease and heartbeat. Mongo is already deployed and the volume is small, so a dedicated broker (Redis with RQ or Celery) would add a service to `docker-compose.yml` for little benefit; an in-process queue was rejected because jobs would be lost on restart.

## Consequences

- The in-memory fallback in `StoryRepository` is not used for queued jobs. If Mongo is down, submissions are refused and not accepted and lost.
- `POST /jobs` returns immediately and replaces the synchronous `/generate-story`. Next.js polls job state, and the duplicated call logic in `route.ts` and `story-generation.ts` becomes a single enqueue call.
- A NotebookLM session that expired or a daily quota that ran out parks Jobs in `needs-login` or `quota-exhausted` and doesn't fail them.
- Jobs carry a `run_after` timestamp so Scheduled generation can be added later.
