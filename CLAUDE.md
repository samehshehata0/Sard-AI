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

- `npm run backend` — equivalent to `cd backend && python run.py` (uvicorn on `127.0.0.1:8000`, reload on)
- `npm run auth` — `cd backend && python save_auth.py`, captures a Playwright storage-state login for NotebookLM (interactive, run manually when the session expires)
- `cd backend && .venv/bin/pytest` — run backend tests
- `cd backend && .venv/bin/pytest tests/test_video_pipeline.py -k name` — single backend test

## Architecture: two coexisting systems

This repo currently contains **two separate, not-yet-merged backends**. Don't assume code in one applies to the other.

### 1. Story generation pipeline (what actually runs today)

`src/app/api/stories/route.ts` is the live feature. Flow:

1. Request hits `POST /api/stories` (or `GET` to list). Identity is an anonymous `sard_user_id` HttpOnly cookie minted on first request — **not** the session system described below.
2. `src/lib/story-repository.ts` persists a `StoryDocument` (see `src/lib/story-types.ts`) via the raw `mongodb` driver (`src/lib/db.ts`, global-cached `MongoClient`), collection scoped by that cookie's user id.
3. The route returns `202` immediately, then does the real work in `after()` (fire-and-forget Next.js background callback): it POSTs to the **Python FastAPI backend** in `backend/` at `PYTHON_BACKEND_URL` (default `http://127.0.0.1:8000`) via a raw `node:http` request, and updates story progress/status as the backend responds.
4. The Python backend (`backend/app/main.py`, router in `backend/app/api/endpoints.py`) drives a Playwright automation of Google NotebookLM to generate a slide presentation, extracts slides (`pymupdf`/`python-pptx`), builds narration audio (Google Cloud TTS or the HF/Edge-TTS fallback in `backend/app/services/narration_service.py`), composes video with `ffmpeg` (`video_composer.py`), validates media (`media_validation.py`), and uploads results to ImageKit. Tunable pipeline constants (slide counts, durations, retry limits, video/audio specs) live in `backend/app/core/config.py`, overridable via env vars listed in `.env.example`.
5. `backend/save_auth.py` produces the Playwright `storage_state.json` NotebookLM login the automation depends on — must be re-run manually when that session expires; there's no auto-refresh.

Both `src/app/api/stories/route.ts` and `src/lib/services/story-generation.ts` independently implement the "call Python backend, map its response into `StoryScene[]`, save" logic — check both before changing this flow, they can drift.

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
