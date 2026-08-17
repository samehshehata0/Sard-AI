import { getDb } from "@/lib/db";
import type { GenerationLog, StoryDocument, StoryInput, StoryScene } from "@/lib/story-types";

const storiesCollection = async () => (await getDb()).collection<StoryDocument>("stories");

export async function createStory(story: StoryDocument) {
  const stories = await storiesCollection();
  await stories.insertOne(story);
}

export async function getStoryForUser(id: string, userId: string) {
  return (await storiesCollection()).findOne({ _id: id, userId });
}

export async function listStoriesForUser(userId: string) {
  try {
    return await (await storiesCollection()).find(
      { userId },
      { projection: { _id: 1, status: 1, progress: 1, currentStep: 1, error: 1, input: 1, sceneCount: 1, createdAt: 1, updatedAt: 1 } },
    ).sort({ createdAt: -1 }).toArray();
  } catch (err) {
    console.warn("[Sard] MongoDB listStoriesForUser notice, returning empty list:", err);
    return [];
  }
}

export async function updateStoryProgress(id: string, progress: number, currentStep: string) {
  await (await storiesCollection()).updateOne(
    { _id: id },
    { $set: { status: "generating", progress, currentStep, updatedAt: new Date() } },
  );
}

export async function appendStoryLog(id: string, log: Omit<GenerationLog, "at">) {
  const entry: GenerationLog = { at: new Date(), ...log };
  console[log.level === "error" ? "error" : "info"](`[Sard][${id}] ${log.message}`);
  await (await storiesCollection()).updateOne(
    { _id: id },
    { $push: { logs: { $each: [entry], $slice: -150 } }, $set: { updatedAt: new Date() } },
  );
}

export async function saveGeneratedScript(
  id: string,
  values: Pick<StoryDocument, "script" | "characters" | "visualStyleGuide" | "scenes">,
) {
  await (await storiesCollection()).updateOne({ _id: id }, { $set: { ...values, updatedAt: new Date() } });
}

export async function saveScenePrompts(id: string, prompts: Array<Pick<StoryScene, "number" | "imagePrompt" | "imageGenerationPrompt" | "videoPrompt">>) {
  const story = await (await storiesCollection()).findOne({ _id: id });
  if (!story) throw new Error("لم يتم العثور على القصة أثناء حفظ مطالبات المشاهد.");

  const promptMap = new Map(prompts.map((prompt) => [prompt.number, prompt]));
  const scenes = story.scenes.map((scene) => {
    const prompt = promptMap.get(scene.number);
    if (!prompt) throw new Error(`لا توجد مطالبة للمشهد ${scene.number}.`);
    return {
      ...scene,
      imagePrompt: prompt.imagePrompt,
      imageGenerationPrompt: prompt.imageGenerationPrompt,
      videoPrompt: prompt.videoPrompt,
    };
  });

  await (await storiesCollection()).updateOne({ _id: id }, { $set: { scenes, updatedAt: new Date() } });
}

export async function saveSceneNarrations(id: string, narrations: Array<Pick<StoryScene, "number" | "narration">>) {
  const story = await (await storiesCollection()).findOne({ _id: id });
  if (!story) throw new Error("لم يتم العثور على القصة أثناء حفظ النصوص المشكّلة.");

  const narrationMap = new Map(narrations.map((scene) => [scene.number, scene.narration]));
  const scenes = story.scenes.map((scene) => {
    const narration = narrationMap.get(scene.number);
    if (!narration) throw new Error(`لا يوجد نص مشكّل للمشهد ${scene.number}.`);
    return { ...scene, narration, narrationVocalized: true };
  });

  await (await storiesCollection()).updateOne({ _id: id }, { $set: { scenes, updatedAt: new Date() } });
}

export async function saveSceneNarration(id: string, sceneNumber: number, narration: string) {
  const result = await (await storiesCollection()).updateOne(
    { _id: id, "scenes.number": sceneNumber },
    { $set: { "scenes.$.narration": narration, "scenes.$.narrationVocalized": true, updatedAt: new Date() } },
  );
  if (!result.matchedCount) throw new Error(`تعذر حفظ النص الصوتي للمشهد ${sceneNumber}.`);
}

export async function saveSceneAsset(id: string, sceneNumber: number, field: "imageUrl" | "audioUrl" | "videoUrl", value: string) {
  const values: Record<string, unknown> = { [`scenes.$.${field}`]: value, updatedAt: new Date() };
  if (field === "audioUrl") values["scenes.$.audioDurationMatched"] = true;
  const result = await (await storiesCollection()).updateOne(
    { _id: id, "scenes.number": sceneNumber },
    { $set: values },
  );
  if (!result.matchedCount) throw new Error(`تعذر حفظ أصل المشهد ${sceneNumber}.`);
}

export async function saveSceneVideoAsset(id: string, sceneNumber: number, value: string) {
  const result = await (await storiesCollection()).updateOne(
    { _id: id, "scenes.number": sceneNumber },
    { $set: { "scenes.$.videoUrl": value, "scenes.$.videoGenerator": "zerogpu-wan2.2-i2v", updatedAt: new Date() } },
  );
  if (!result.matchedCount) throw new Error(`تعذر حفظ فيديو المشهد ${sceneNumber}.`);
}

export async function completeStory(id: string, assets: StoryDocument["assets"]) {
  await (await storiesCollection()).updateOne(
    { _id: id },
    {
      $set: {
        status: "completed",
        progress: 100,
        currentStep: "اكتمل إنشاء القصة والأصول المنفصلة.",
        assets,
        completedAt: new Date(),
        updatedAt: new Date(),
      },
    },
  );
}

export async function failStory(id: string, error: string) {
  await (await storiesCollection()).updateOne(
    { _id: id },
    { $set: { status: "failed", error, currentStep: "توقف التوليد بسبب خطأ.", updatedAt: new Date() } },
  );
}

export async function resetStoryForRetry(id: string, userId: string) {
  const result = await (await storiesCollection()).updateOne(
    { _id: id, userId, status: "failed" },
    {
      $set: { status: "queued", progress: 0, currentStep: "أُعيدت محاولة التوليد من آخر مرحلة مكتملة.", updatedAt: new Date() },
      $unset: { error: "" },
    },
  );
  return result.modifiedCount === 1;
}

export function createQueuedStory(id: string, userId: string, input: StoryInput, totalDurationSeconds: number, sceneCount: number): StoryDocument {
  const now = new Date();
  return {
    _id: id,
    userId,
    input,
    status: "queued",
    progress: 0,
    currentStep: "تم إنشاء طلب التوليد.",
    totalDurationSeconds,
    sceneCount,
    scenes: [],
    assets: {},
    logs: [{ at: now, level: "info", message: "تم إنشاء طلب القصة وانتظار بدء المعالجة." }],
    createdAt: now,
    updatedAt: now,
  };
}
