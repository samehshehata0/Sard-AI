import "server-only";
import {
  completeStory,
  failStory,
  getStoryForUser,
  saveGeneratedScript,
  updateStoryProgress,
} from "@/lib/story-repository";
import { AppError } from "@/server/errors/app-error";
import type { StoryAssets, StoryDocument, StoryInput, StoryScene } from "@/lib/story-types";

const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || "http://127.0.0.1:8000";
// Enqueueing and reading a Job are quick calls; generation itself runs in the Python worker.
const REQUEST_TIMEOUT_MS = 10_000;

// "failed" cannot be fixed by retrying; "dead_letter" used every attempt and waits for an admin.
export type JobState = "queued" | "running" | "completed" | "failed" | "dead_letter";

interface PythonScene {
  scene_number?: number;
  title?: string;
  duration_seconds?: number;
  narration_text?: string;
  visual_description?: string;
  image_url?: string;
}

export interface JobResult {
  scenes?: PythonScene[];
  duration_seconds?: number;
  presentation_url?: string;
  video_url?: string;
  thumbnail_url?: string;
  narration_audio_url?: string;
}

export interface JobView {
  job_id: string;
  story_id?: string;
  state: JobState;
  progress?: number;
  step?: string | null;
  error?: string | null;
  result?: JobResult | null;
}

type JobInput = StoryInput & { custom_instructions?: string };

const UNREACHABLE = "تعذر الاتصال بخدمة التوليد. يرجى المحاولة بعد قليل.";
const QUEUE_UNAVAILABLE = "قائمة الانتظار غير متاحة مؤقتًا. يرجى المحاولة بعد قليل.";

async function backendFetch(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${PYTHON_BACKEND_URL}${path}`, {
      ...init,
      cache: "no-store",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    throw AppError.providerFailure(UNREACHABLE);
  }
}

export function buildJobPayload(storyId: string, jobId: string, input: JobInput) {
  return {
    job_id: jobId,
    story_id: storyId,
    story_title: input.title,
    story_idea: input.topic,
    education_level: input.stage,
    story_duration: input.duration,
    learning_objectives: input.objectives,
    student_age: input.age,
    student_level: input.level,
    learning_needs: input.needs,
    story_style: input.style,
    voice_tone: input.tone,
    narrator_gender: input.speakerGender,
    output_type: input.output,
    custom_instructions: input.custom_instructions ?? "",
  };
}

/** Queue a generation Job. Throws an AppError, with an Arabic message, if it was not accepted. */
export async function enqueueStoryJob(storyId: string, jobId: string, input: JobInput): Promise<void> {
  const response = await backendFetch("/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildJobPayload(storyId, jobId, input)),
  });
  if (response.status === 503) throw AppError.databaseUnavailable(QUEUE_UNAVAILABLE);
  if (!response.ok) throw AppError.providerFailure("تعذر إضافة طلب التوليد إلى قائمة الانتظار.");
}

/** The Job, or null if the backend does not know it. */
export async function fetchJob(jobId: string): Promise<JobView | null> {
  const response = await backendFetch(`/jobs/${encodeURIComponent(jobId)}`);
  if (response.status === 404) return null;
  if (!response.ok) throw AppError.providerFailure(UNREACHABLE);
  return (await response.json()) as JobView;
}

/** Turn a finished Job's result into the story's scenes and assets. */
export function mapJobResultToStory(input: StoryInput, result: JobResult): { scenes: StoryScene[]; assets: StoryAssets } {
  const scenes: StoryScene[] = Array.isArray(result.scenes) && result.scenes.length > 0
    ? result.scenes.map((scene, index) => ({
        number: scene.scene_number || index + 1,
        title: scene.title || `المشهد ${index + 1}`,
        durationSeconds: scene.duration_seconds || 8,
        narration: scene.narration_text || input.topic,
        visualDescription: scene.visual_description || `شريحة إنفوجرافيك ${index + 1}`,
        imagePrompt: input.topic,
        videoPrompt: input.topic,
        imageUrl: scene.image_url || result.thumbnail_url || undefined,
        audioUrl: result.narration_audio_url || undefined,
        videoUrl: result.video_url || undefined,
      }))
    : [
        {
          number: 1,
          title: input.title,
          durationSeconds: result.duration_seconds || 15,
          narration: `${input.title}. ${input.topic}.`,
          visualDescription: `عرض تقديمي لشريحة ${input.title}`,
          imagePrompt: input.topic,
          videoPrompt: input.topic,
          imageUrl: result.thumbnail_url || undefined,
          audioUrl: result.narration_audio_url || undefined,
          videoUrl: result.video_url || undefined,
        },
      ];

  return {
    scenes,
    assets: {
      presentationUrl: result.presentation_url || undefined,
      videoUrl: result.video_url || undefined,
      thumbnailUrl: result.thumbnail_url || undefined,
      combinedAudioUrl: result.narration_audio_url || undefined,
      combinedVideoUrl: result.video_url || undefined,
      combinedNarratedVideoUrl: result.video_url || undefined,
    },
  };
}

const ACTIVE = new Set<StoryDocument["status"]>(["queued", "generating"]);

export function isAwaitingJob(story: Pick<StoryDocument, "jobId" | "status">): boolean {
  return Boolean(story.jobId) && ACTIVE.has(story.status);
}

/**
 * Bring a story up to date with its Job. Called when the story is read, so it
 * keeps working across restarts: nothing waits in the background for the Job.
 * If the backend cannot be reached the story is returned unchanged and the next
 * read tries again.
 */
export async function syncStoryWithJob(story: StoryDocument, userId: string): Promise<StoryDocument> {
  if (!isAwaitingJob(story) || !story.jobId) return story;

  let job: JobView | null;
  try {
    job = await fetchJob(story.jobId);
  } catch {
    return story;
  }

  if (job === null) {
    await failStory(story._id, "تعذر العثور على طلب التوليد. يرجى إعادة المحاولة.");
  } else if (job.state === "running") {
    const progress = job.progress ?? 25;
    if (story.status !== "generating" || story.progress < progress) {
      await updateStoryProgress(story._id, progress, job.step || "جارٍ التوليد...");
    }
  } else if (job.state === "completed") {
    const { scenes, assets } = mapJobResultToStory(story.input, job.result ?? {});
    await saveGeneratedScript(story._id, {
      script: `## ${story.input.title}\n\n${story.input.topic}`,
      scenes,
    });
    await completeStory(story._id, assets);
  } else if (job.state === "failed" || job.state === "dead_letter") {
    await failStory(story._id, job.error || "توقف التوليد بسبب خطأ.");
  } else if (job.state === "queued" && job.step && story.currentStep !== job.step) {
    // Queued again after a failed stage: say so instead of freezing on the old step.
    await updateStoryProgress(story._id, Math.max(story.progress, 25), job.step);
  } else {
    return story;
  }

  return (await getStoryForUser(story._id, userId)) ?? story;
}
