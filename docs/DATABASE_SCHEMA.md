# Database schema

MongoDB collection names use Mongoose defaults (`users`, `projects`, `generationjobs`, `assessments`, and `reports`). All IDs are ObjectIds and all models use timestamps.

## User

| Field | Type | Rules |
|---|---|---|
| `fullName` | string | required, trimmed, 2–100 |
| `email` | string | required, trimmed, lowercase, maximum 254 |
| `passwordHash` | string | required, excluded from normal selection and JSON |
| `role` | enum | `student_teacher`, `faculty_member`, `supervisor`, `admin` |
| `institution` | string | optional, maximum 150 |
| `avatarUrl` | string | optional, maximum 2,048 |
| `isActive` | boolean | required, default true |
| `createdAt`, `updatedAt` | date | automatic |

Index: unique ascending `email` (`users_email_unique`).

## AuthSession

| Field | Type | Rules |
|---|---|---|
| `userId` | ObjectId | required, references User |
| `tokenHash` | string | required, unique HMAC digest; raw cookie token is never stored |
| `expiresAt` | date | required, checked on every session lookup |
| `createdAt`, `updatedAt` | date | automatic |

Indexes:

- Unique `{ tokenHash: 1 }` (`auth_sessions_token_unique`).
- TTL `{ expiresAt: 1 }` (`auth_sessions_expiry_ttl`).
- `{ userId: 1 }` (`auth_sessions_user`) for revoking a user's sessions.

## Project

Contains the requested educational inputs, `audio|video` requested outputs, provider output URLs, error state, and status:

`draft | ready | processing | completed | partially_completed | failed`

Index: `{ userId: 1, createdAt: -1 }` (`projects_user_created_at`) for dashboard/history queries.

## GenerationJob

Stores project/user ownership, `video|audio` type, provider identifiers, opaque request payload, lifecycle status, output/error, retry count (`0..10`), and completion time.

Indexes:

- `{ projectId: 1, status: 1 }` (`generation_jobs_project_status`)
- `{ userId: 1, createdAt: -1 }` (`generation_jobs_user_created_at`)

Provider request payloads may contain operational input but must never contain provider keys. Apply encryption or field minimization if sensitive learner data is introduced.

## Assessment

Stores project/user ownership, stress and motivation answers (each value `1..5`), and server-calculated scores (`0..100`).

Index: `{ userId: 1, projectId: 1, createdAt: -1 }` (`assessments_user_project_created_at`).

The questionnaire version and expected answer counts should be added when the assessment instrument is finalized.

## Report

Stores project/user ownership, progress and well-being scores (`0..100`), and up to 50 recommendations.

Indexes:

- Unique `{ projectId: 1 }` (`reports_project_unique`) for one current report per project.
- `{ userId: 1, createdAt: -1 }` (`reports_user_created_at`).

If report history is later required, remove the unique project constraint and add a version or generated-at ordering rule through a migration.

## Referential integrity

MongoDB does not enforce foreign keys. Service operations must:

- Verify referenced users/projects exist and are owned by the authenticated user.
- Delete dependent records/assets through an explicit cleanup workflow.
- Use transactions when a multi-document state transition must be atomic.
- Never trust `userId` supplied in a client body; derive it from the authenticated session.
