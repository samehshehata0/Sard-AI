import { randomUUID } from "node:crypto";
import {
  createQueuedStory,
  createStory,
  failStory,
  listStoriesForUser,
} from "@/lib/story-repository";
import { requireStoryUserId } from "@/lib/story-auth";
import { enqueueStoryJob, isAwaitingJob, syncStoryWithJob } from "@/lib/services/job-queue";
import { assertSameOrigin } from "@/server/security/request-origin";
import { apiSuccess } from "@/server/responses/api-response";
import { handleApiError } from "@/server/errors/error-handler";
import { AppError } from "@/server/errors/app-error";
import type { StoryDocument } from "@/lib/story-types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface StoryRequestBody {
  title?: string;
  topic?: string;
  stage?: string;
  duration?: string;
  objectives?: string[] | string;
  age?: string;
  level?: string;
  needs?: string;
  style?: string;
  tone?: string;
  speakerGender?: "male" | "female";
  output?: string;
  custom_instructions?: string;
}

export async function GET() {
  try {
    const userId = await requireStoryUserId();
    let stories = await listStoriesForUser(userId);

    // Stories still waiting on a Job are brought up to date before they are listed.
    const waiting = (stories as unknown as StoryDocument[]).filter(isAwaitingJob);
    if (waiting.length > 0) {
      await Promise.allSettled(waiting.slice(0, 10).map((story) => syncStoryWithJob(story, userId)));
      stories = await listStoriesForUser(userId);
    }

    return apiSuccess({ stories });
  } catch (error) {
    return handleApiError(error, { route: "GET /api/stories" });
  }
}

export async function POST(request: Request) {
  try {
    assertSameOrigin(request);
    const userId = await requireStoryUserId();

    let body: StoryRequestBody;
    try {
      body = await request.json() as StoryRequestBody;
    } catch {
      throw AppError.validation(undefined, "بيانات الطلب ليست JSON صالحاً.");
    }

    const storyId = randomUUID();
    const jobId = randomUUID();

    const inputData = {
      title: body.title || body.topic || "قصة تعليمية جديدة",
      topic: body.topic || body.title || "",
      stage: body.stage || "المرحلة الابتدائية",
      duration: body.duration || "تلقائي حسب المحتوى",
      objectives: Array.isArray(body.objectives) ? body.objectives : [body.objectives || "التعلم الذكي"],
      age: body.age || "8 سنوات",
      level: body.level || "مبتدئ",
      needs: body.needs || "لا يوجد",
      style: body.style || "رسوم ثلاثية الأبعاد",
      tone: body.tone || "ودود ومرح",
      speakerGender: body.speakerGender || "female",
      output: body.output || "نص + صوت + فيديو",
      custom_instructions: body.custom_instructions || "",
    };

    try {
      await createStory(createQueuedStory(storyId, userId, inputData, 60, 1, jobId));
    } catch (err) {
      console.error("[Sard] Could not save the story:", err);
      throw AppError.databaseUnavailable();
    }

    // The Job is queued and this request returns; the Python worker does the rest.
    try {
      await enqueueStoryJob(storyId, jobId, inputData);
    } catch (err) {
      const message = err instanceof AppError ? err.message : "تعذر إضافة طلب التوليد إلى قائمة الانتظار.";
      await failStory(storyId, message).catch(() => {});
      throw err;
    }

    return apiSuccess({ storyId, status: "queued", sceneCount: 1 }, "تم إنشاء طلب التوليد بنجاح.", { status: 202 });
  } catch (error) {
    return handleApiError(error, { route: "POST /api/stories" });
  }
}
