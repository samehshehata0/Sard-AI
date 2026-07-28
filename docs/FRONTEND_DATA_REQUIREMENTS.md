# Frontend data requirements audit

## Audit boundary

Reviewed all routes and reusable components under `src/app` and `src/components`. No route, layout, Arabic copy, RTL setting, brand style, color, or component layout was redesigned.

## Route inventory

| Route | Data displayed or submitted | Backend source |
|---|---|---|
| `/` | Static marketing features and navigation | Frontend static content |
| `/login` | Email, password, remember-me; loading/error state | `POST /api/auth/login` |
| `/register` | Full name, email, password, role; loading/error state | `POST /api/auth/register` |
| `/dashboard` | Current user name, recent projects, project counts/quality, latest well-being summary | `GET /api/auth/me`, `GET /api/projects`, latest assessment/report aggregation |
| `/history` | Searchable/filterable/paginated project cards | `GET /api/projects` |
| `/profile` | Full name, email, role, institution, avatar | `GET /api/auth/me` |
| `/settings` | Theme plus notification/AI/audio preferences | Theme is local; other preferences need a future user-preferences endpoint |
| `/stories/new` | Project title/topic, objectives, learner profile, style, tone, outputs, prompt | `POST /api/projects`; generation endpoints after project creation |
| `/stories/:id/editor` | Project title, editable story text, characters, objectives, suggestions | `GET/PATCH /api/projects/:id`; see gaps below |
| `/stories/:id/storyboard` | Ordered scene title, visual description, narration, media prompt, status | Project detail extension or a future scenes endpoint |
| `/stories/:id/video` | Project video URL/status, generation status, ordered scene timeline | Project detail + video generation endpoints |
| `/stories/:id/audio` | Project audio URL/status, voice configuration, scene narration | Project detail + audio generation endpoints |
| `/stories/:id/reports` | Overall/progress/well-being and category scores, strengths, improvements, recommendations | `GET /api/projects/:id/report` |
| `not-found` / loading routes | No domain data | Frontend only |

## Component-level requirements

- `AppHeader`, `AppSidebar`: authenticated user identity is currently visual-only and should eventually receive `User`.
- `StoryCard`: `id`, `title`, `educationalTopic`, localized status, `createdAt`, quality score, summary. The view adapter currently preserves existing Arabic labels.
- `WizardForm`: maps UI fields to `CreateProjectInput`; uses submit loading and normalized error messages.
- `StoryEditor`: project title, generated story content, characters, objectives, and suggestions.
- `SceneCard`: scene number/title, visual direction, Arabic narration, provider prompt, review status.
- `VideoPlayerCard`: generation action, status, `videoUrl`, download availability, retry action.
- `AudioPlayerCard`: generation action, `audioUrl`, duration/progress, voice, speed, tone, retry/settings actions.
- `WellBeingIndexCard`: `stressScore`, `motivationScore`, `wellBeingScore`, recommendation/note.
- `ReportScoreCard`: score label, `0..100` value, allowlisted icon identifier.
- Authentication and project forms need idle/loading/success/error states. `AsyncState<T>` and normalized `ApiError` define the shared shape.

## Centralized service layer

The frontend now accesses backend-ready data through:

- `api-client.ts`: JSON transport, credential support, optional bearer token, response unwrapping, and error normalization.
- `auth-service.ts`
- `projects-service.ts`
- `generations-service.ts`
- `assessments-service.ts`
- `reports-service.ts`

`NEXT_PUBLIC_API_URL` is the only public backend configuration. If it is absent, service methods use centralized `mock-data.ts`, keeping the current interface functional. No browser code contains or accepts AI-provider secrets, and no service calls an AI provider directly.

## Mock dependencies found

| Previous source | Consumers | Current disposition |
|---|---|---|
| `stories-data.ts` | Dashboard, history, story cards | Centralized project service/card adapter |
| `editor-data.ts` | Story editor | Centralized project service editor adapter |
| `scenes-data.ts` | Storyboard, video timeline, audio narration | Centralized project service scene adapter |
| `report-data.ts` | Report route | Centralized report service |
| `dashboard-data.ts` | Dashboard stats and well-being card | Centralized temporary dashboard mock |
| Inline profile values | Profile and dashboard greeting | Centralized auth service mock |
| Inline audio/video placeholders | Media player components | Still presentation placeholders pending real jobs/URLs |
| Inline settings defaults | Settings page | Still local UI defaults; no requested endpoint exists |
| `landing-data.ts` | Public landing feature cards | Retained as static product copy, not API data |

The legacy constant files remain in the repository so no working data is silently deleted, but domain screens no longer import them.

## Contract gaps exposed by the existing UI

The required endpoint list covers core MVP persistence and audio/video generation, but these existing screens require additional backend decisions:

1. Story editor fields (`storyContent`, `characters`, `suggestions`) are not present on the required `Project` model. Either extend `Project` or add a versioned project-content resource.
2. Storyboard scenes have no model or endpoint in the requested contract. If storyboards remain in scope, add `GET/PATCH /api/projects/:id/scenes`.
3. Dashboard aggregate statistics need either calculation from paginated projects/reports or `GET /api/dashboard/summary`.
4. Profile editing needs `PATCH /api/users/me`.
5. Persistent settings need `GET/PATCH /api/users/me/preferences`.
6. Report UI needs `overall`, category `scores`, `strengths`, and `improvements` in addition to the minimum Report model.
7. PDF export needs either client-side generation from report data or `GET /api/projects/:id/report.pdf`.
8. The current UI mentions text/story generation and image/storyboard generation, while the stated MVP AI scope only permits external video and Arabic audio generation. These controls should remain mock/no-op until product scope explicitly adds backend capabilities.

These gaps are documented only; no unrequested endpoint or backend has been implemented.

## Mapping notes

- Arabic labels are view concerns. API enums remain stable English identifiers and are mapped at the service/component boundary.
- UI `topic` maps to `educationalTopic`; `objectives` to `learningObjectives`; `age` to `learnerAge`; `stage` to `educationLevel`; `needs` to `learnerCharacteristics`; `style` to `storyStyle`; `tone` to `voiceTone`; and `output` to `requestedOutputs`.
- The wizard’s duration and learner `level` currently have no dedicated Project properties; they are preserved in the temporary prompt mapping. The backend model should add explicit fields if they must be searchable/reportable.
- Media polling should use GenerationJob, not hold requests open while a provider works.
