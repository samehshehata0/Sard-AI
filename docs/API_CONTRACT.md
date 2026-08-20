# سَرْد AI — REST API Contract

## 1. Scope and conventions

This contract covers the MVP backend consumed by the existing Arabic RTL frontend. The browser calls only the سَرْد backend. Provider secrets and all audio/video provider calls remain server-side.

- Base URL: `NEXT_PUBLIC_API_URL` + `/api`
- Content type: `application/json; charset=utf-8`
- Authentication: opaque, revocable server-side session using the `sard_session` HTTP-only cookie. Bearer tokens and browser storage are not used.
- Dates: ISO 8601 UTC strings.
- IDs: opaque non-empty strings. Clients must not infer type or ownership from an ID.
- JSON field names: camelCase.
- All protected resources are scoped to the authenticated user. A resource owned by another user should return `404` to avoid leaking its existence.

Successful single-resource response:

```json
{ "success": true, "data": { "id": "project_123" }, "message": "تم تنفيذ الطلب بنجاح." }
```

Successful paginated response:

```json
{
  "success": true,
  "data": [],
  "message": "تم تنفيذ الطلب بنجاح.",
  "meta": {
    "page": 1,
    "pageSize": 20,
    "totalItems": 0,
    "totalPages": 0
  }
}
```

Error response:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "بعض البيانات غير صالحة.",
    "details": { "email": "البريد الإلكتروني غير صالح." },
    "requestId": "req_123"
  }
}
```

## 2. Shared domain schemas

### User

```ts
interface User {
  id: string;
  fullName: string;
  email: string;
  role: "student_teacher" | "faculty_member" | "supervisor";
  institution: string | null;
  avatarUrl: string | null;
  createdAt: string;
  updatedAt: string;
}
```

### Project

```ts
interface Project {
  id: string;
  userId: string;
  title: string;
  educationalTopic: string;
  learningObjectives: string[];
  learnerAge: string;
  educationLevel: string;
  learnerCharacteristics: string;
  storyStyle: string;
  voiceTone: string;
  requestedOutputs: ("audio" | "video")[];
  prompt: string;
  status: "draft" | "ready" | "processing" | "completed" | "partially_completed" | "failed";
  videoUrl: string | null;
  audioUrl: string | null;
  thumbnailUrl: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}
```

Project status transitions:

`draft → ready → processing → completed | partially_completed | failed`. A failed project may return to `ready` after retry preparation. `completed` means every requested output has completed; `partially_completed` means one output succeeded and another failed. `errorMessage` is non-null only for failed outcomes.

### GenerationJob

```ts
interface GenerationJob {
  id: string;
  projectId: string;
  type: "video" | "audio";
  provider: string;
  providerJobId: string | null;
  status: "queued" | "processing" | "completed" | "failed" | "cancelled";
  outputUrl: string | null;
  errorMessage: string | null;
  createdAt: string;
  completedAt: string | null;
}
```

`outputUrl` is present only for `completed`; `errorMessage` only for `failed`; `completedAt` for terminal states. Provider names and IDs are informational and must never expose credentials.

### Assessment

```ts
interface Assessment {
  id: string;
  projectId: string;
  userId: string;
  stressAnswers: number[];
  motivationAnswers: number[];
  stressScore: number;
  motivationScore: number;
  wellBeingScore: number;
  createdAt: string;
}
```

### Report

```ts
interface Report {
  id: string;
  projectId: string;
  progressScore: number;
  wellBeingScore: number;
  recommendations: string[];
  createdAt: string;
}
```

The current report screen additionally requires `overall`, `scores`, `strengths`, and `improvements`. The backend should include them in the report response:

```ts
interface ReportView extends Report {
  overall: number;
  scores: Array<{
    label: string;
    value: number;
    icon: "book" | "sparkles" | "play" | "file" | "heart";
  }>;
  strengths: string[];
  improvements: string[];
}
```

## 3. Validation

- All strings are trimmed. Unless stated otherwise, strings must be 1–500 characters.
- `fullName`: 2–100 characters.
- `email`: valid address, normalized to lowercase, maximum 254 characters.
- `password`: 8–128 characters. Passwords are write-only and never returned.
- `institution`: optional, maximum 150 characters.
- `title`: 1–150 characters.
- `educationalTopic`: 1–500 characters.
- `learningObjectives`: 1–20 items; each item 1–500 characters.
- `learnerAge`: 1–50 characters.
- `educationLevel`, `storyStyle`, `voiceTone`: 1–100 characters.
- `learnerCharacteristics`: 1–1,000 characters.
- `requestedOutputs`: unique non-empty values from `audio | video`.
- `prompt`: maximum 10,000 characters. The server constructs a safe prompt if omitted.
- URL fields: absolute HTTPS URLs (HTTP may be accepted only in local development).
- Assessment arrays: exactly the count defined by the versioned questionnaire; each integer is 1–5. The server calculates all scores; client-supplied scores are rejected.
- All score fields: integer or decimal in `0..100`.
- Unknown request fields should be rejected with `VALIDATION_ERROR` to catch client/server drift.

## 4. Authentication

### `POST /api/auth/register`

Public. Creates an account and session.

Request:

```json
{
  "fullName": "سامح أحمد",
  "email": "sameh@university.edu",
  "password": "strong-password",
  "confirmPassword": "strong-password",
  "role": "student_teacher"
}
```

`role` accepts `student_teacher | faculty_member | supervisor`; public registration can never create an admin. Names accept Arabic and English Unicode letters, marks, spaces, apostrophes, periods, underscores, and hyphens. The password is 8–128 characters and must contain at least one letter and one digit.

Response `201`: `{ "success": true, "data": { "user": User }, "message": "تم إنشاء الحساب بنجاح." }` and `Set-Cookie`.

Errors: `400 VALIDATION_ERROR`, `409 CONFLICT`, `429 RATE_LIMITED`.

### `POST /api/auth/login`

Public.

Request:

```json
{ "email": "sameh@university.edu", "password": "strong-password" }
```

Response `200`: `{ "success": true, "data": { "user": User }, "message": "تم تسجيل الدخول بنجاح." }` and session cookie. Unknown emails, wrong passwords, and inactive accounts all return the same Arabic message and status.

Errors: `400 VALIDATION_ERROR`, `401 AUTHENTICATION_ERROR`, `429 RATE_LIMITED`.

### `POST /api/auth/logout`

No body. Invalidates the current session when present and expires its cookie. The operation is safe to repeat.

Response `200`: success envelope with `data: null`.

### `GET /api/auth/me`

Authenticated.

Response `200`: success envelope containing the sanitized User. `passwordHash` is never selected or serialized.

Errors: `401 AUTHENTICATION_ERROR`.

### `PATCH /api/auth/profile`

Authenticated. At least one field is required:

```json
{
  "fullName": "سامح أحمد",
  "institution": "كلية التربية",
  "avatarUrl": "https://cdn.example.com/avatar.jpg"
}
```

`institution` and `avatarUrl` may be `null` to clear them. Email, role, activation state, password hash, and IDs cannot be changed through this endpoint.

Response `200`: success envelope containing the updated sanitized User.

Errors: `400 VALIDATION_ERROR`, `401 AUTHENTICATION_ERROR`, `404 NOT_FOUND`.

### Session cookie

- Name: `sard_session`.
- Value: 256-bit opaque random token; only an HMAC-SHA-256 digest is stored in MongoDB.
- Lifetime: 30 minutes.
- Attributes: `HttpOnly`, `SameSite=Lax`, `Path=/`, and `Secure` in production.
- Expired/revoked/unknown tokens are treated as unauthenticated.
- The session collection has a MongoDB TTL index for eventual cleanup. Every authorization check also compares `expiresAt`, so security does not depend on TTL cleanup timing.

## 5. Projects

### `POST /api/projects`

Authenticated.

Request:

```json
{
  "title": "رحلة قطرة ماء",
  "educationalTopic": "أهمية الحفاظ على الماء",
  "learningObjectives": ["أن يشرح المتعلم أهمية ترشيد استهلاك الماء."],
  "learnerAge": "9-11 سنة",
  "educationLevel": "المرحلة الابتدائية",
  "learnerCharacteristics": "أمثلة بصرية وحوار قصير",
  "storyStyle": "حواري",
  "voiceTone": "مشجعة",
  "requestedOutputs": ["audio", "video"],
  "prompt": "قصة عربية تعليمية مدتها أربع دقائق"
}
```

Response `201`: `{ "data": Project }`, initially `draft`. Creating a project does not call an external AI provider.

Errors: `400 VALIDATION_ERROR`, `401 UNAUTHENTICATED`, `413 PAYLOAD_TOO_LARGE`, `429 RATE_LIMITED`.

### `GET /api/projects`

Authenticated. Query parameters:

- `page`: integer ≥ 1, default `1`.
- `pageSize`: integer `1..100`, default `20`.
- `status`: one Project status.
- `search`: 1–100 characters; matches title/topic.
- `sort`: `createdAt | updatedAt | title`, default `updatedAt`.
- `order`: `asc | desc`, default `desc`.

Response `200`: paginated `Project[]`. Stable sorting must use `id` as a secondary key.

Errors: `400 VALIDATION_ERROR`, `401 UNAUTHENTICATED`.

### `GET /api/projects/:id`

Authenticated. Response `200`: `{ "data": Project }`.

Errors: `401 UNAUTHENTICATED`, `404 PROJECT_NOT_FOUND`.

### `PATCH /api/projects/:id`

Authenticated. Accepts one or more mutable fields from the create request. IDs, ownership, status, output URLs, errors, and timestamps are server-managed. Updating prompt inputs after generation should set the project to `draft` without deleting completed assets; the backend may require explicit regeneration.

Response `200`: `{ "data": Project }`.

Errors: `400 VALIDATION_ERROR`, `401 UNAUTHENTICATED`, `404 PROJECT_NOT_FOUND`, `409 PROJECT_NOT_EDITABLE`.

### `DELETE /api/projects/:id`

Authenticated. Cancels active jobs where supported and removes or schedules removal of associated assets.

Response `204`.

Errors: `401 UNAUTHENTICATED`, `404 PROJECT_NOT_FOUND`, `409 PROJECT_HAS_ACTIVE_GENERATION`.

## 6. Generation

The backend owns provider selection, private keys, polling/webhooks, output validation, and durable file storage. The browser never calls a provider directly.

### `POST /api/projects/:id/generate/video`

Authenticated.

Request (all optional):

```json
{ "prompt": "حافظ على الأسلوب الكرتوني الهادئ", "aspectRatio": "16:9" }
```

`aspectRatio`: `16:9 | 9:16 | 1:1`. Response `202`: `{ "data": GenerationJob }` with `type: "video"` and usually `queued`.

Errors: `400 VALIDATION_ERROR`, `401 UNAUTHENTICATED`, `404 PROJECT_NOT_FOUND`, `409 GENERATION_ALREADY_ACTIVE`, `422 PROJECT_NOT_READY`, `429 GENERATION_LIMIT_REACHED`, `503 PROVIDER_UNAVAILABLE`.

### `POST /api/projects/:id/generate/audio`

Authenticated.

Request:

```json
{ "prompt": "نطق عربي فصيح", "voice": "ar-calm", "speed": 1, "tone": "مشجعة" }
```

`voice`: backend allowlisted identifier; `speed`: `0.5..2`; `tone`: maximum 100 characters. Response `202`: GenerationJob with `type: "audio"`.

Errors: same as video.

### `GET /api/generations/:id`

Authenticated. Used for polling. Response `200`: `{ "data": GenerationJob }`.

Recommended polling: after 2 seconds, exponential backoff capped at 15 seconds, stop at a terminal status. The backend may include `Retry-After`.

Errors: `401 UNAUTHENTICATED`, `404 GENERATION_NOT_FOUND`.

### `POST /api/generations/:id/retry`

Authenticated. No body. Allowed only for `failed` or `cancelled` jobs. Creates and returns a new job; it must not mutate the historical failed job.

Response `202`: `{ "data": GenerationJob }`.

Errors: `401 UNAUTHENTICATED`, `404 GENERATION_NOT_FOUND`, `409 GENERATION_NOT_RETRYABLE`, `429 GENERATION_LIMIT_REACHED`, `503 PROVIDER_UNAVAILABLE`.

## 7. Assessments

### `POST /api/projects/:id/assessments`

Authenticated.

Request:

```json
{
  "stressAnswers": [2, 2, 1],
  "motivationAnswers": [5, 4, 4]
}
```

Response `201`: `{ "data": Assessment }`. Scores are calculated server-side using the questionnaire version active at submission.

Errors: `400 VALIDATION_ERROR`, `401 UNAUTHENTICATED`, `404 PROJECT_NOT_FOUND`.

### `GET /api/projects/:id/assessments/latest`

Authenticated. Response `200`: `{ "data": Assessment }`.

Errors: `401 UNAUTHENTICATED`, `404 PROJECT_NOT_FOUND`, `404 ASSESSMENT_NOT_FOUND`.

## 8. Reports

### `GET /api/projects/:id/report`

Authenticated. Returns the latest report representation required by the current UI.

Response `200`: `{ "data": ReportView }`.

Errors: `401 UNAUTHENTICATED`, `404 PROJECT_NOT_FOUND`, `404 REPORT_NOT_FOUND`, `409 REPORT_NOT_READY`.

## 9. Error/status reference

| HTTP | Typical code | Meaning |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Request fields or query parameters are invalid |
| 401 | `AUTHENTICATION_ERROR` | Missing, invalid, expired session, or generic invalid credentials |
| 403 | `AUTHORIZATION_ERROR` | Authenticated but role is not allowed |
| 404 | `*_NOT_FOUND` | Resource does not exist or is not visible |
| 409 | `*_NOT_EDITABLE`, `*_ALREADY_ACTIVE` | Current resource state conflicts |
| 413 | `PAYLOAD_TOO_LARGE` | JSON body exceeds server limit |
| 422 | `PROJECT_NOT_READY` | Valid request, incomplete project prerequisites |
| 429 | `RATE_LIMITED`, `GENERATION_LIMIT_REACHED` | Retry later; include `Retry-After` |
| 500 | `INTERNAL_ERROR` | Unexpected server error |
| 502 | `PROVIDER_ERROR` | Provider returned an invalid/error response |
| 503 | `PROVIDER_UNAVAILABLE` | Provider temporarily unavailable |
| 504 | `PROVIDER_TIMEOUT` | Provider did not respond in time |

The frontend normalizes every non-2xx response into `ApiError(status, code, message, details, requestId)`. User messages must be safe and Arabic-ready; provider stack traces, credentials, and raw sensitive responses must never be returned.

## 10. Security and operational requirements

- Use HTTPS, secure HTTP-only same-site cookies, CSRF protection when cross-site deployment requires it, and strict CORS allowlisting.
- Never place provider or private API keys in `NEXT_PUBLIC_*`.
- Validate ownership on every project, generation, assessment, and report operation.
- Use idempotency keys or active-job constraints for generation requests to prevent duplicate billing.
- Store provider outputs in controlled durable storage; return short-lived signed URLs if assets are private.
- Rate-limit authentication and generation endpoints.
- Log `requestId`, internal error, provider, and provider job ID server-side without logging passwords, cookies, tokens, or full sensitive prompts.
