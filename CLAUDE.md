# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Next.js 16 in this repo has breaking changes vs. what your training data expects (e.g. `src/proxy.ts` replaces `middleware.ts`). Check `node_modules/next/dist/docs/` before relying on remembered Next.js API shapes.

## Commands

Frontend (run from repo root):

- `npm run dev` — Next.js dev server
- `npm run build` / `npm run start` — production build / serve
- `npm run lint` — ESLint (flat config, `eslint-config-next`)
- `npm run typecheck` — `tsc --noEmit`
- `npm run test` — Vitest, runs everything under `tests/`
- `npx vitest run tests/auth-routes.test.ts` — single test file
- `npx vitest run tests/auth-routes.test.ts -t "test name"` — single test case

Python backend (video/NotebookLM pipeline, in `backend/`, has its own `.venv`):

- `npm run backend` — runs `backend/run.py` through `scripts/run-python.mjs`, which finds a Python with the backend's packages (`backend/.venv` or `.venv`, then `python3`, then `python`; a stock macOS has no `python`) and prints the setup steps if there is none (uvicorn on `127.0.0.1:8000`, reload on; this one process serves the API **and** runs the job worker)
- `docker compose up --build` — web app, backend (API + worker) and MongoDB together; see the comments in `docker-compose.yml` for sharing the NotebookLM login (`NOTEBOOKLM_STORAGE_STATE_PATH=auth/storage_state.json`)
- `npm run auth` — runs `backend/save_auth.py` the same way; captures a Playwright storage-state login for NotebookLM (interactive, run manually when the session expires)
- `npm run canary` — `backend/notebooklm_canary.py [--notebook-url URL]` (pass arguments after `--`), checks the live NotebookLM UI against the locator registry (`backend/app/automation/notebooklm_ui.py`) and reports which strategy matches per element; exits non-zero if a required element is missing (needs the saved login, exits 2 if it expired)
- `cd backend && .venv/bin/pytest` — run backend tests
- `cd backend && .venv/bin/pytest tests/test_video_pipeline.py -k name` — single backend test

## Architecture: two coexisting systems

This repo currently contains **two separate, not-yet-merged backends**. Don't assume code in one applies to the other.

### 1. Story generation pipeline (what actually runs today)

`src/app/api/stories/route.ts` is the live feature. Flow:

1. Request hits `POST /api/stories` (or `GET` to list). Identity is an anonymous `sard_user_id` HttpOnly cookie minted on first request — **not** the session system described below.
2. `src/lib/story-repository.ts` persists a `StoryDocument` (see `src/lib/story-types.ts`) via the raw `mongodb` driver (`src/lib/db.ts`, global-cached `MongoClient`), collection scoped by that cookie's user id.
3. The route saves the story, queues a **Job** by calling `POST /jobs` on the Python backend (`src/lib/services/job-queue.ts`, `PYTHON_BACKEND_URL`, default `http://127.0.0.1:8000`) and returns `202` immediately. If the queue cannot take the Job (Mongo down, backend unreachable) the story is marked failed and the request gets an Arabic `503`/`502`. The retry route queues a fresh Job the same way.
4. Jobs live in the MongoDB `jobs` collection (`backend/app/services/job_repository.py`). There is deliberately **no in-memory fallback** for Jobs, unlike `StoryRepository`. A worker started with the FastAPI app (`backend/app/services/job_worker.py`, setting `JOB_WORKER_ENABLED`) claims the oldest queued Job, one at a time, and runs the pipeline as **Stages** (`backend/app/services/pipeline.py`: notebooklm_submit, notebooklm_collect, extract_slides, narrate, compose, upload). Each Stage's output is saved on the Job, so a failed Stage is retried on its own and finished Stages are reused: up to `JOB_STAGE_MAX_ATTEMPTS` (3) tries with backoff (`JOB_RETRY_BACKOFF_SECONDS`, 30 s / 2 min / 10 min), transient errors only. The Job goes back in the queue with `run_after`, so the worker is free for other Jobs meanwhile. Errors retrying cannot fix mark the Job `failed`; a Job that uses every attempt becomes `dead_letter`, keeping its error and evidence (`failures` on the Job), and can be requeued with `POST /jobs/{id}/requeue` (header `X-Admin-Token`, setting `JOB_ADMIN_TOKEN`; off if unset). **Submit** (the shared browser creates the notebook, adds the story and asks for the Slide Deck) saves the notebook URL on the Job the moment the notebook exists, so a retry or a replacement worker carries on in that notebook; **Collect** opens it from the URL, waits for the deck, downloads it and then deletes the notebook (a failed delete is only logged). There is no `notebooklm_job.json` any more. `JOB_WORKER_CONCURRENCY` worker loops run at once (default 1), so with more workers one Job can narrate while another waits on NotebookLM. All NotebookLM browser work goes through **one long-lived browser** (`backend/app/services/browser_host.py`, `get_browser_host()`): it stays open and signed in, each Submit/Collect opens a fresh tab in it and closes the tab afterwards, and it lives on one dedicated thread, so browser work is serial (a free account generates one deck at a time anyway; `NOTEBOOKLM_BROWSER_CONCURRENCY` no longer adds browsers). It is rebuilt if Chrome dies, when `npm run auth` changes the login file, and every `NOTEBOOKLM_BROWSER_RECYCLE_HOURS` (12); it closes with the app. See `docs/adr/0003-one-shared-notebooklm-browser.md`. See `docs/adr/0001-mongodb-job-queue-for-generation.md` and `docs/adr/0002-split-notebooklm-submit-and-collect.md`.
Temp files: a Job's working folder is `TEMP_DIR/<story_id>`. When a Job completes, everything the result does not link to is deleted (scene images and any locally served media stay: they are fetched through `/temp/...`); a cancelled Job's folder is removed; the folders of failed, dead-lettered and cancelled Jobs are kept for `JOB_TEMP_RETENTION_DAYS` (7) so an admin can requeue them, then purged (`backend/app/services/temp_cleanup.py`). Job ids must be path-safe (`story_id` is validated), because they name that folder.

Parking: when NotebookLM's login has expired (`NeedsLoginError`) or it refuses new decks (`QuotaExhaustedError`), the Job is **parked** (`needs_login` / `quota_exhausted`), not failed, and the attempt it was on is given back so outages never use up retries. The first Job to hit it sets a flag in the `service_state` collection and parks every waiting Job that still needs NotebookLM; Jobs about to open a browser check the flag first. Jobs resume by themselves: after `npm run auth` rewrites `storage_state.json` (newer than the flag), or when the quota's `resume_at` passes (`NOTEBOOKLM_QUOTA_RESET_UTC`, else an hourly probe via `NOTEBOOKLM_QUOTA_PROBE_MINUTES`). `GET /notebooklm/status` shows the flag and how many Jobs wait, and the log says `NotebookLM LOGIN EXPIRED … Run npm run auth`. Quota detection needs `NOTEBOOKLM_QUOTA_MARKERS` (the refusal wording, from ticket #13). The story shows `blockedReason` in Arabic. Parked Jobs still count toward a user's limit and can be cancelled.

Fairness (`POST /jobs` takes the web app's `user_id`): jobs run oldest first; a user may have at most `JOB_MAX_ACTIVE_PER_USER` (2) queued or running jobs (429 with an Arabic message beyond that); a request identical to one of their active jobs (same fingerprint, backed by a unique index) is not queued twice and returns the existing job with `duplicate: true`; and `POST /jobs/{id}/cancel` cancels a job still waiting (409 once a worker has it). In `POST /api/stories` the queue is asked first and the story is created only if the job was accepted, so refusals and duplicates leave no orphan story. `POST /api/stories/[id]/cancel` is the user-facing cancel.
5. Nothing waits in the background for a Job. The story is brought up to date when it is read: `GET /api/stories/[id]` and `GET /api/stories` call `syncStoryWithJob`, which reads `GET /jobs/{id}` and moves the story to generating, completed or failed. This keeps working across Next.js restarts.
6. The pipeline (`backend/app/services/pipeline.py`) drives a Playwright automation of Google NotebookLM to generate a slide presentation, extracts slides (`pymupdf`/`python-pptx`), builds narration audio (Google Cloud TTS or the HF/Edge-TTS fallback in `backend/app/services/narration_service.py`), composes video with `ffmpeg` (`video_composer.py`), validates media (`media_validation.py`), and uploads results to ImageKit. Tunable pipeline constants (slide counts, durations, retry limits, video/audio specs) live in `backend/app/core/config.py`, overridable via env vars listed in `.env.example`.
7. `backend/save_auth.py` produces the Playwright `storage_state.json` NotebookLM login the automation depends on — must be re-run manually when that session expires; there's no auto-refresh.

There is no synchronous generation endpoint any more: everything goes through `POST /jobs`.

### 2. Documented REST/auth contract (partially implemented, aspirational beyond auth)

`docs/API_CONTRACT.md`, `docs/BACKEND_ARCHITECTURE.md`, `docs/DATABASE_SCHEMA.md`, and `docs/FRONTEND_DATA_REQUIREMENTS.md` describe a `User`/`Project`/`GenerationJob`/`Assessment`/`Report` REST API backed by Mongoose (`src/server/database/models/*`) with a real `sard_session` cookie (HMAC-hashed, 30-minute TTL, `src/server/auth/session.ts`).

Only the auth slice of this contract is actually built: `/api/auth/{register,login,logout,me,profile}` under `src/app/api/auth/`, backed by `src/server/auth/*` and `src/server/database/connection.ts` (a _second_, Mongoose-based DB connection, cached on `globalThis`, separate from `src/lib/db.ts`'s raw driver connection). `/api/projects`, `/api/generations`, `/api/assessments`, `/api/projects/:id/report` from the contract **do not exist yet** — `docs/FRONTEND_DATA_REQUIREMENTS.md` § "Contract gaps" enumerates what's still missing. Most of the UI (dashboard stats, story editor, storyboard, reports) currently reads from `src/services/mock-data.ts` via `src/services/*-service.ts`, which is used automatically whenever `NEXT_PUBLIC_API_URL` is unset.

`src/server/config/env.ts` validates `AI_VIDEO_PROVIDER`/`AI_AUDIO_PROVIDER`/`AI_VIDEO_API_KEY`/`AI_AUDIO_API_KEY`/`AUTH_SECRET`/`MONGODB_URI` for this contract's future generation endpoints — those provider vars aren't in `.env.example` and aren't wired to anything yet; don't assume `getServerEnv()` is called anywhere outside tests.

When adding a feature, check which of these two systems it belongs to before picking where to put it and which DB/auth primitives to reuse.

## Conventions worth knowing

- All user-facing strings (errors, success messages, UI copy) are Arabic; the app is RTL-first. Keep new user-facing text in Arabic and route error messages through the existing envelope shape (`{ success, data|error, message }` for the `/api/auth/*` family — see `src/server/responses/api-response.ts` and `src/server/errors/*`).
- `server-only` is imported at the top of sensitive server modules (`env.ts`, `auth.service.ts`, etc.) to keep them out of client bundles. Vitest aliases `server-only` to `tests/server-only.ts` (see `vitest.config.ts`) so these modules are testable under Node.
- `next.config.ts` externalizes `ffmpeg-static` from the server bundle (it resolves a platform binary at runtime) and allowlists `ik.imagekit.io` for `next/image`.
- Path alias `@/*` → `src/*` (both `tsconfig.json` and `vitest.config.ts`).

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues (samehshehata0/Sard-AI), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five canonical triage labels used as-is. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (CONTEXT.md + docs/adr/ at repo root). See `docs/agents/domain.md`.
