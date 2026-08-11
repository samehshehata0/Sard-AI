import "server-only";
import { request as httpRequest } from "node:http";
import {
  completeStory,
  failStory,
  getStoryForUser,
  saveGeneratedScript,
  updateStoryProgress,
} from "@/lib/story-repository";
import type { StoryScene } from "@/lib/story-types";

const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || "http://127.0.0.1:8000";

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

export async function runStoryGeneration(storyId: string, userId: string) {
  try {
    const story = await getStoryForUser(storyId, userId);
    if (!story) throw new Error("القصة غير موجودة.");

    await updateStoryProgress(storyId, 25, "جارٍ تشغيل أتمتة Google NotebookLM بالكامل...").catch(() => {});

    const payload = {
      story_id: storyId,
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

    const result = await postJsonToPythonBackend(`${PYTHON_BACKEND_URL}/generate-story`, payload);
    if (!result.ok) {
      const errText = typeof result.body === "object" ? result.body?.detail || JSON.stringify(result.body) : result.body;
      throw new Error(String(errText));
    }

    await updateStoryProgress(storyId, 75, "تم استخراج العرض التقديمي والشرائح والصوت، جارٍ الإكمال...").catch(() => {});

    const data = result.body;
    const scenes: StoryScene[] = [
      {
        number: 1,
        title: story.input.title,
        durationSeconds: data.duration_seconds || 15,
        narration: `${story.input.title}. ${story.input.topic}.`,
        visualDescription: `عرض تلقائي مولد بواسطة Google NotebookLM.`,
        imagePrompt: story.input.topic,
        videoPrompt: story.input.topic,
        imageUrl: data.thumbnail_url || data.presentation_url || undefined,
        audioUrl: data.video_url || undefined,
        videoUrl: data.video_url || undefined,
      },
    ];

    await saveGeneratedScript(storyId, {
      script: `## ${story.input.title}\n\n${story.input.topic}`,
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

    console.info(`[Sard][${storyId}] NotebookLM generation finished successfully.`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`[Sard][${storyId}] Generation error:`, message);
    await failStory(storyId, message).catch(() => {});
  }
}

export async function rebuildStoryVideoToRequestedDuration(storyId: string, userId: string) {
  return runStoryGeneration(storyId, userId);
}
