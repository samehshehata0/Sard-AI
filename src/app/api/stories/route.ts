import { randomUUID } from "node:crypto";
import { request as httpRequest } from "node:http";
import { after } from "next/server";
import {
  createQueuedStory,
  createStory,
  updateStoryProgress,
  saveGeneratedScript,
  completeStory,
  failStory,
  listStoriesForUser,
} from "@/lib/story-repository";
import { requireStoryUserId } from "@/lib/story-auth";
import { assertSameOrigin } from "@/server/security/request-origin";
import { apiSuccess } from "@/server/responses/api-response";
import { handleApiError } from "@/server/errors/error-handler";
import { AppError } from "@/server/errors/app-error";
import type { StoryScene } from "@/lib/story-types";

export const runtime = "nodejs";
export const maxDuration = 900;
export const dynamic = "force-dynamic";

const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || "http://127.0.0.1:8000";

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

interface PythonScene {
  scene_number?: number;
  title?: string;
  duration_seconds?: number;
  narration_text?: string;
  visual_description?: string;
  image_url?: string;
}

interface PythonResponseBody {
  detail?: string;
  scenes?: PythonScene[];
  duration_seconds?: number;
  presentation_url?: string;
  video_url?: string;
  thumbnail_url?: string;
  narration_audio_url?: string;
}

function postJsonToPythonBackend(url: string, payload: unknown): Promise<{ ok: boolean; status: number; body: PythonResponseBody | string }> {
  return new Promise((resolve, reject) => {
    const parsedUrl = new URL(url);
    const postData = JSON.stringify(payload);

    const req = httpRequest(
      {
        hostname: parsedUrl.hostname,
        port: parsedUrl.port || 8000,
        path: parsedUrl.pathname,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(postData),
        },
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => {
          try {
            const parsed = JSON.parse(data) as PythonResponseBody;
            resolve({ ok: !!(res.statusCode && res.statusCode >= 200 && res.statusCode < 300), status: res.statusCode || 500, body: parsed });
          } catch {
            resolve({ ok: false, status: res.statusCode || 500, body: data });
          }
        });
      }
    );

    req.on("error", (err) => reject(err));
    req.setTimeout(0);
    req.write(postData);
    req.end();
  });
}

export async function GET() {
  try {
    const userId = await requireStoryUserId();
    const stories = await listStoriesForUser(userId);
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
      await createStory(createQueuedStory(storyId, userId, inputData, 60, 1));
    } catch (err) {
      console.warn("[Sard] Local database write warning:", err);
    }

    const payload = {
      story_id: storyId,
      story_title: inputData.title,
      story_idea: inputData.topic,
      education_level: inputData.stage,
      story_duration: inputData.duration,
      learning_objectives: inputData.objectives,
      student_age: inputData.age,
      student_level: inputData.level,
      learning_needs: inputData.needs,
      story_style: inputData.style,
      voice_tone: inputData.tone,
      narrator_gender: inputData.speakerGender,
      output_type: inputData.output,
      custom_instructions: inputData.custom_instructions,
    };

    after(async () => {
      try {
        console.info(`[Sard] Starting background Python automation for storyId: ${storyId}`);
        await updateStoryProgress(storyId, 25, "جارٍ أتمتة Google NotebookLM وإنشاء العرض التقديمي والشرائح...").catch(() => {});

        const result = await postJsonToPythonBackend(`${PYTHON_BACKEND_URL}/generate-story`, payload);
        if (!result.ok) {
          const errText = typeof result.body === "object" ? result.body?.detail || JSON.stringify(result.body) : result.body;
          console.error(`[Sard][${storyId}] Generation failed: ${errText}`);
          await failStory(storyId, String(errText)).catch(() => {});
          return;
        }
        if (typeof result.body === "string") {
          await failStory(storyId, "استجابة خدمة التوليد غير صالحة.").catch(() => {});
          return;
        }

        await updateStoryProgress(storyId, 75, "تم استخراج الشرائح وتجميع الصوت والفيديو، جارٍ تجهيز الأصول النهائي...").catch(() => {});

        const data = result.body;
        const scenes: StoryScene[] = Array.isArray(data.scenes) && data.scenes.length > 0
          ? data.scenes.map((s, idx) => ({
              number: s.scene_number || idx + 1,
              title: s.title || `المشهد ${idx + 1}`,
              durationSeconds: s.duration_seconds || 8,
              narration: s.narration_text || inputData.topic,
              visualDescription: s.visual_description || `شريحة إنفوجرافيك ${idx + 1}`,
              imagePrompt: inputData.topic,
              videoPrompt: inputData.topic,
              imageUrl: s.image_url || data.thumbnail_url || undefined,
              audioUrl: data.narration_audio_url || undefined,
              videoUrl: data.video_url || undefined,
            }))
          : [
              {
                number: 1,
                title: inputData.title,
                durationSeconds: data.duration_seconds || 15,
                narration: `${inputData.title}. ${inputData.topic}.`,
                visualDescription: `عرض تقديمي لشريحة ${inputData.title}`,
                imagePrompt: inputData.topic,
                videoPrompt: inputData.topic,
                imageUrl: data.thumbnail_url || undefined,
                audioUrl: data.narration_audio_url || undefined,
                videoUrl: data.video_url || undefined,
              },
            ];

        await saveGeneratedScript(storyId, {
          script: `## ${inputData.title}\n\n${inputData.topic}`,
          scenes,
        }).catch(() => {});

        await completeStory(storyId, {
          presentationUrl: data.presentation_url || undefined,
          videoUrl: data.video_url || undefined,
          thumbnailUrl: data.thumbnail_url || undefined,
          combinedAudioUrl: data.narration_audio_url || undefined,
          combinedVideoUrl: data.video_url || undefined,
          combinedNarratedVideoUrl: data.video_url || undefined,
        }).catch(() => {});

        console.info(`[Sard][${storyId}] Background generation completed successfully with ${scenes.length} scenes.`);
      } catch (err) {
        console.error(`[Sard][${storyId}] Background generation exception:`, err);
        await failStory(storyId, String(err)).catch(() => {});
      }
    });

    return apiSuccess({ storyId, status: "queued", sceneCount: 1 }, "تم إنشاء طلب التوليد بنجاح.", { status: 202 });
  } catch (error) {
    return handleApiError(error, { route: "POST /api/stories" });
  }
}
