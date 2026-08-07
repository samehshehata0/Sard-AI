import { request as httpRequest } from "node:http";
import { after } from "next/server";
import {
  getStoryForUser,
  resetStoryForRetry,
  updateStoryProgress,
  saveGeneratedScript,
  completeStory,
  failStory,
} from "@/lib/story-repository";
import type { StoryScene } from "@/lib/story-types";

export const runtime = "nodejs";
export const maxDuration = 900;
export const dynamic = "force-dynamic";

const USER_COOKIE = "sard_user_id";
const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || "http://127.0.0.1:8000";

function getUserId(request: Request) {
  const cookieHeader = request.headers.get("cookie") || "";
  return cookieHeader.match(new RegExp(`(?:^|;\\s*)${USER_COOKIE}=([^;]+)`))?.[1];
}

function postJsonToPythonBackend(url: string, payload: any): Promise<{ ok: boolean; status: number; body: any }> {
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
        res.on("data", (chunk) => { data += chunk; });
        res.on("end", () => {
          try {
            const parsed = JSON.parse(data);
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

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const userId = getUserId(request);
  if (!userId) return Response.json({ error: "تعذر تحديد مستخدم القصة." }, { status: 401 });

  const { id } = await context.params;
  try {
    const story = await getStoryForUser(id, userId);
    if (!story) return Response.json({ error: "القصة غير موجودة أو لا تملك صلاحية الوصول إليها." }, { status: 404 });
    if (story.status !== "failed") return Response.json({ error: "لا يمكن إعادة المحاولة إلا لقصة توقفت بسبب خطأ." }, { status: 409 });
    if (!(await resetStoryForRetry(id, userId))) return Response.json({ error: "تعذر تجهيز القصة لإعادة المحاولة." }, { status: 409 });

    const payload = {
      story_id: id,
      story_title: story.input.title,
      story_idea: story.input.topic,
      education_level: story.input.stage,
      story_duration: story.input.duration,
      learning_objectives: story.input.objectives,
      student_age: story.input.age,
      student_level: story.input.level,
      learning_needs: story.input.needs,
      story_style: story.input.style,
      voice_tone: story.input.tone,
      narrator_gender: story.input.speakerGender,
      output_type: story.input.output,
    };

    after(async () => {
      try {
        console.info(`[Sard] Retrying NotebookLM Python generation for storyId: ${id}`);
        await updateStoryProgress(id, 25, "أعيدت المحاولة — جارٍ أتمتة Google NotebookLM...").catch(() => {});

        const result = await postJsonToPythonBackend(`${PYTHON_BACKEND_URL}/generate-story`, payload);
        if (!result.ok) {
          const errText = typeof result.body === "object" ? result.body?.detail || JSON.stringify(result.body) : result.body;
          console.error(`[Sard][${id}] Retry generation failed: ${errText}`);
          await failStory(id, String(errText)).catch(() => {});
          return;
        }

        await updateStoryProgress(id, 75, "أعيدت المحاولة — جارٍ تجهيز مقطع الفيديو والأصول...").catch(() => {});

        const data = result.body;
        const scenes: StoryScene[] = Array.isArray(data.scenes) && data.scenes.length > 0
          ? data.scenes.map((s: any, idx: number) => ({
              number: s.scene_number || idx + 1,
              title: s.title || `المشهد ${idx + 1}`,
              durationSeconds: s.duration_seconds || 8,
              narration: s.narration_text || story.input.topic,
              visualDescription: s.visual_description || `شريحة إنفوجرافيك ${idx + 1}`,
              imagePrompt: story.input.topic,
              videoPrompt: story.input.topic,
              imageUrl: s.image_url || data.thumbnail_url || undefined,
              audioUrl: data.video_url || undefined,
              videoUrl: data.video_url || undefined,
            }))
          : [
              {
                number: 1,
                title: story.input.title,
                durationSeconds: data.duration_seconds || 15,
                narration: `${story.input.title}. ${story.input.topic}.`,
                visualDescription: `عرض تقديمي لشريحة ${story.input.title}`,
                imagePrompt: story.input.topic,
                videoPrompt: story.input.topic,
                imageUrl: data.thumbnail_url || undefined,
                audioUrl: data.video_url || undefined,
                videoUrl: data.video_url || undefined,
              },
            ];

        await saveGeneratedScript(id, {
          script: `## ${story.input.title}\n\n${story.input.topic}`,
          scenes,
        }).catch(() => {});

        await completeStory(id, {
          presentationUrl: data.presentation_url || undefined,
          videoUrl: data.video_url || undefined,
          thumbnailUrl: data.thumbnail_url || undefined,
          combinedAudioUrl: data.video_url || undefined,
          combinedVideoUrl: data.video_url || undefined,
          combinedNarratedVideoUrl: data.video_url || undefined,
        }).catch(() => {});

        console.info(`[Sard][${id}] Retry NotebookLM generation completed successfully with ${scenes.length} scenes.`);
      } catch (err) {
        console.error(`[Sard][${id}] Retry generation exception:`, err);
        await failStory(id, String(err)).catch(() => {});
      }
    });

    return Response.json({ status: "queued" }, { status: 202 });
  } catch (error) {
    console.error(`[Sard][${id}] تعذرت إعادة محاولة التوليد:`, error);
    return Response.json({ error: "تعذرت إعادة محاولة التوليد. راجع طرفية الخادم للتفاصيل." }, { status: 500 });
  }
}
