import { randomUUID } from "node:crypto";
import { request as httpRequest } from "node:http";
import { after } from "next/server";
import {
  createQueuedStory,
  createStory,
  ensureUser,
  updateStoryProgress,
  saveGeneratedScript,
  completeStory,
  failStory,
  listStoriesForUser,
} from "@/lib/story-repository";
import type { StoryScene } from "@/lib/story-types";

export const runtime = "nodejs";
export const maxDuration = 900;
export const dynamic = "force-dynamic";

const USER_COOKIE = "sard_user_id";
const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || "http://127.0.0.1:8000";

function getOrCreateUserId(request: Request) {
  const cookieHeader = request.headers.get("cookie") || "";
  const existing = cookieHeader.match(new RegExp(`(?:^|;\\s*)${USER_COOKIE}=([^;]+)`))?.[1];
  return { userId: existing || `anonymous-${randomUUID()}`, isNew: !existing };
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
        res.on("data", (chunk) => {
          data += chunk;
        });
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

export async function GET(request: Request) {
  const { userId } = getOrCreateUserId(request);
  try {
    const stories = await listStoriesForUser(userId);
    return Response.json({ stories });
  } catch (err) {
    console.error("[Sard] Failed listing stories:", err);
    return Response.json({ stories: [] });
  }
}

export async function POST(request: Request) {
  let body: any;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "بيانات الطلب ليست JSON صالحاً." }, { status: 400 });
  }

  const { userId, isNew } = getOrCreateUserId(request);
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
    await ensureUser(userId);
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

      await updateStoryProgress(storyId, 75, "تم استخراج الشرائح وتجميع الصوت والفيديو، جارٍ تجهيز الأصول النهائي...").catch(() => {});

      const data = result.body;
      const scenes: StoryScene[] = Array.isArray(data.scenes) && data.scenes.length > 0
        ? data.scenes.map((s: any, idx: number) => ({
            number: s.scene_number || idx + 1,
            title: s.title || `المشهد ${idx + 1}`,
            durationSeconds: s.duration_seconds || 8,
            narration: s.narration_text || inputData.topic,
            visualDescription: s.visual_description || `شريحة إنفوجرافيك ${idx + 1}`,
            imagePrompt: inputData.topic,
            videoPrompt: inputData.topic,
            imageUrl: s.image_url || data.thumbnail_url || undefined,
            audioUrl: data.video_url || undefined,
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
              audioUrl: data.video_url || undefined,
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
        combinedAudioUrl: data.video_url || undefined,
        combinedVideoUrl: data.video_url || undefined,
        combinedNarratedVideoUrl: data.video_url || undefined,
      }).catch(() => {});

      console.info(`[Sard][${storyId}] Background generation completed successfully with ${scenes.length} scenes.`);
    } catch (err) {
      console.error(`[Sard][${storyId}] Background generation exception:`, err);
      await failStory(storyId, String(err)).catch(() => {});
    }
  });

  const response = Response.json(
    {
      storyId,
      status: "queued",
      sceneCount: 1,
    },
    { status: 202 }
  );

  if (isNew) {
    response.headers.append(
      "Set-Cookie",
      `${USER_COOKIE}=${encodeURIComponent(userId)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000${
        process.env.NODE_ENV === "production" ? "; Secure" : ""
      }`
    );
  }
  return response;
}
