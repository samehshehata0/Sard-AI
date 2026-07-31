# سَرْد AI backend architecture

## Runtime

The backend foundation uses Next.js 16 App Router Route Handlers, TypeScript, Mongoose, MongoDB Atlas, and Zod. It remains part of the existing full-stack application; no Express server or second runtime is introduced.

```text
Browser
  → /api/* Route Handler
    → validation and authentication/authorization boundary
      → server service / data-access layer
        → cached Mongoose connection
          → MongoDB Atlas
        → external audio/video provider (future)
```

Provider requests must originate from server-only modules. The browser only receives sanitized DTOs and generation job state.

## Server modules

- `server/config/env.ts`: validates server configuration with Zod. Validation is lazy so static frontend builds remain possible, while every database/provider/auth entry point must call `getServerEnv()` before use.
- `server/database/connection.ts`: caches both resolved connections and in-flight connection promises on `globalThis`. This prevents duplicate development connections and shares connection setup within a warm serverless instance.
- `server/database/models/*`: Mongoose schemas, validation, timestamps, and indexes.
- `server/auth/session.ts`: creates, resolves, requires, role-checks, and revokes database-backed sessions.
- `server/auth/auth.service.ts`: password hashing, generic credential verification, registration, and profile updates.
- `server/auth/rate-limit.ts`: basic per-instance login throttling keyed by client address and normalized email.
- `server/errors/*`: operational error taxonomy and one response boundary for Zod, known, and unexpected errors.
- `server/responses/api-response.ts`: consistent success/failure envelopes.
- `server/validation/common.schemas.ts`: shared ObjectId/pagination validation and a bounded JSON reader.
- `server/security/ownership.ts`: ownership assertion and query filter primitives. Future handlers must include `userId` in database filters, not rely only on a prior page check.
- `server/logging/logger.ts`: structured technical logs with recursive redaction of passwords, hashes, tokens, cookies, secrets, API keys, and prompts.

All sensitive server modules import `server-only` to prevent accidental inclusion in client component graphs.

## Authentication and authorization

Passwords use bcrypt with cost factor 12. The browser receives a 256-bit opaque token in an HTTP-only `sard_session` cookie; MongoDB stores only an HMAC-SHA-256 digest created with `AUTH_SECRET`. Sessions expire after 30 minutes and are revocable on logout.

`createSession`, `getCurrentUser`, `requireUser`, `requireRole`, and `clearSession` are the reusable session boundary. Public registration accepts only student teacher, faculty member, or supervisor; the `admin` role remains available for controlled administrative provisioning.

The Next.js 16 `src/proxy.ts` performs only an optimistic cookie-presence redirect for protected page prefixes. It does not access MongoDB and does not treat the cookie as authoritative. Protected layouts resolve the session from MongoDB, and backend Route Handlers must independently call `requireUser`/`requireRole` and query owned resources with both their ID and authenticated `userId`.

The in-memory login limiter provides immediate basic protection (five attempts per address/email window). Multi-instance production deployment should replace or supplement it with a shared Redis/database-backed limiter and trusted proxy configuration.

## API lifecycle

Future mutating Route Handlers should:

1. Authenticate the request.
2. Parse with `parseJsonBody()` and a strict feature schema.
3. Query resources using the authenticated `userId`.
4. Enforce role and ownership again at the mutation boundary.
5. Return a minimal DTO using `apiSuccess()`.
6. Pass exceptions to `handleApiError()` with non-sensitive route/request context.

Default JSON payload limit is 100 KB. Provider callbacks may use a separately justified limit and signature verification.

## Health endpoint

`GET /api/health` runs dynamically on the Node.js runtime. It reports:

- API status.
- `connected` or `disconnected` database status.
- UTC timestamp.

It returns HTTP `200` when MongoDB is connected and `503` when disconnected. It never returns connection strings, provider configuration, keys, stack traces, host details, or database names.

## Security boundaries

- All secret variables are unprefixed server variables. Only `NEXT_PUBLIC_API_URL` is browser-visible.
- Password hashes are `select: false` and removed by the User JSON transform.
- Raw Mongoose documents should never be returned directly; future handlers must map them to explicit DTOs.
- Prompts, credentials, provider payloads, and tokens must not be logged.
- Generation APIs should add persistent rate limiting, idempotency keys, active-job constraints, provider webhook signature verification, and retry caps.
- Authentication uses secure-in-production, HTTP-only, SameSite=Lax cookies. Same-site mutation endpoints must continue to reject cross-origin deployment patterns unless explicit CSRF protection is added.

## Environment and deployment

Copy `.env.example` to an ignored local environment file and replace every placeholder. Atlas access must be restricted by least-privilege database credentials and an appropriate network access policy.

Production startup/readiness should fail deployment when environment validation fails. The lazy function enables the existing frontend build in environments where backend secrets are intentionally unavailable, but runtime server operations never substitute defaults for secrets.
