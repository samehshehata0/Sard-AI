import "server-only";

import "server-only";

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { copyFile, mkdtemp, readFile, rm, unlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Client, handle_file } from "@gradio/client";
import { InferenceClient } from "@huggingface/inference";
import ffmpegPath from "ffmpeg-static";
import { z } from "zod";
import {
  appendStoryLog,
  completeStory,
  failStory,
  getStoryForUser,
  saveGeneratedScript,
  saveSceneNarration,
  saveSceneNarrations,
  saveSceneAsset,
  saveSceneVideoAsset,
  saveScenePrompts,
  updateStoryProgress,
} from "@/lib/story-repository";
import type { SpeakerGender, StoryInput, StoryScene } from "@/lib/story-types";

const JSON_RESPONSE_MAX_CHARS = 1_500;
const PROVIDER_TIMEOUT_MS = 15 * 60 * 1_000;
const MAX_TEXT_COMPLETION_TOKENS = 16_384;
const SCENES_PER_QWEN_BATCH = 10;
const MAX_SCENES_PER_STORY = 16;
const MIN_SCENE_DURATION_SECONDS = 3;
const MAX_SCENE_DURATION_SECONDS = 5;
const CONCURRENT_SCENE_GENERATIONS = 2;
const MAX_FLUX_ATTEMPTS = 5;
const MAX_WAN_ATTEMPTS = 3;
const MAX_TTS_ATTEMPTS = 6;
const AUDIO_DURATION_TOLERANCE_SECONDS = 0.25;

export const FLUX_ADVERTISEMENT_SPACE = "prithivMLmods/FLUX.2-Klein-LoRA-Studio";
export const FLUX_ADVERTISEMENT_SPACE_URL = "https://prithivmlmods-flux-2-klein-lora-studio.hf.space";
export const WAN_I2V_VIDEO_SPACE = "zerogpu-aoti/wan2-2-fp8da-aoti-faster";
export const WAN_I2V_VIDEO_SPACE_URL = "https://zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space";

const stringOrObjectToString = z.preprocess((val) => {
  if (typeof val === "string") return val.trim();
  if (val && typeof val === "object") {
    return Object.entries(val)
      .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
      .join("\n")
      .trim();
  }
  return String(val ?? "").trim();
}, z.string().min(1));

const generatedSceneSchema = z.object({
  number: z.preprocess((v) => Number(v), z.number().int().positive()),
  title: stringOrObjectToString,
  durationSeconds: z.preprocess((v) => Number(v), z.number().min(MIN_SCENE_DURATION_SECONDS).max(MAX_SCENE_DURATION_SECONDS)),
  narration: stringOrObjectToString,
  visualDescription: stringOrObjectToString,
});

const storyFoundationSchema = z.object({
  script: stringOrObjectToString,
  characters: z.array(z.object({
    name: stringOrObjectToString,
    description: stringOrObjectToString
  })).min(1),
  visualStyleGuide: stringOrObjectToString,
});

const generatedScriptSchema = storyFoundationSchema.extend({ scenes: z.array(generatedSceneSchema).min(1) });
const generatedSceneBatchSchema = z.object({ scenes: z.array(generatedSceneSchema).min(1) });

const generatedPromptSchema = z.object({
  number: z.preprocess((v) => Number(v), z.number().int().positive()),
  imagePrompt: stringOrObjectToString,
  imageGenerationPrompt: z.string().trim().min(1),
  videoPrompt: stringOrObjectToString,
});

const generatedPromptsSchema = z.object({
  prompts: z.array(generatedPromptSchema).min(1),
});

const vocalizedNarrationSchema = z.object({
  number: z.preprocess((v) => Number(v), z.number().int().positive()),
  narration: stringOrObjectToString,
});

const vocalizedNarrationsSchema = z.object({
  scenes: z.array(vocalizedNarrationSchema).min(1),
});

const durationMatchedNarrationSchema = z.object({
  narration: stringOrObjectToString,
});

type GeneratedScript = z.infer<typeof generatedScriptSchema>;
type GeneratedPrompts = z.infer<typeof generatedPromptsSchema>;

let fileEnvMap: Record<string, string> | undefined;

function getFileEnv(name: string): string | undefined {
  if (!fileEnvMap) {
    fileEnvMap = {};
    try {
      const envPath = join(process.cwd(), ".env");
      if (existsSync(envPath)) {
        const lines = readFileSync(envPath, "utf8").split("\n");
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed && !trimmed.startsWith("#")) {
            const eqPos = trimmed.indexOf("=");
            if (eqPos > 0) {
              const k = trimmed.substring(0, eqPos).trim();
              const v = trimmed.substring(eqPos + 1).trim();
              fileEnvMap[k] = v;
            }
          }
        }
      }
    } catch {}
  }
  return fileEnvMap[name];
}

function env(name: string, fallback?: string) {
  const value = getFileEnv(name) || process.env[name] || fallback;
  if (!value) throw new Error(`المتغير ${name} غير مضبوط في ملف .env.`);
  return value;
}

function headersForHf(token: string) {
  return { Authorization: `Bearer ${token}` };
}

function safeProviderText(text: string) {
  return text
    .replace(/hf_[A-Za-z0-9]+/g, "[HF_TOKEN]")
    .replace(/private_[A-Za-z0-9+/=]+/g, "[IMAGEKIT_KEY]")
    .replace(/__sign=[^\s&]+/g, "__sign=[REDACTED]")
    .replace(/eyJ[A-Za-z0-9._-]{20,}/g, "[SIGNED_TOKEN]")
    .replace(/AIzaSy[A-Za-z0-9_-]+/g, "[GEMINI_KEY]")
    .slice(0, JSON_RESPONSE_MAX_CHARS);
}

function formatErrorMessage(error: unknown): string {
  if (!error) return "حدث خطأ غير معروف أثناء توليد القصة.";
  if (typeof error === "string" && error.trim()) return error.trim();
  if (error instanceof Error && error.message?.trim()) return error.message.trim();

  if (typeof error === "object") {
    const record = error as Record<string, unknown>;
    if (typeof record.message === "string" && record.message.trim()) return record.message.trim();
    if (typeof record.message === "object" && record.message) {
      const nested = formatErrorMessage(record.message);
      if (nested && nested !== "حدث خطأ غير معروف أثناء توليد القصة.") return nested;
    }
    if (typeof record.error === "string" && record.error.trim()) return record.error.trim();
    if (typeof record.error === "object" && record.error) {
      const nested = formatErrorMessage(record.error);
      if (nested && nested !== "حدث خطأ غير معروف أثناء توليد القصة.") return nested;
    }
    if (typeof record.stage === "string") {
      return `Gradio Space Error (${record.stage}): ${record.message ? String(record.message) : "Failed"}`;
    }
    if (typeof record.title === "string" && record.title) {
      return typeof record.message === "string" ? `${record.title}: ${record.message}` : record.title;
    }
    try {
      const json = JSON.stringify(error);
      if (json && json !== "{}" && json !== "null") return json;
    } catch {
      // Ignore serialization errors
    }
  }

  return String(error);
}

async function responseText(response: Response) {
  try {
    return safeProviderText(await response.text());
  } catch {
    return "تعذر قراءة تفاصيل الاستجابة.";
  }
}

async function requestJson(url: string, init: RequestInit, service: string): Promise<unknown> {
  console.info(`[Sard][API] ${service}: ${init.method || "GET"} ${url}`);
  let response: Response;
  try {
    response = await fetch(url, { ...init, signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS) });
  } catch (error) {
    throw new Error(`تعذر الاتصال بخدمة ${service}: ${error instanceof Error ? error.message : "خطأ شبكة غير معروف"}`);
  }
  if (!response.ok) {
    throw new Error(`فشلت خدمة ${service} (${response.status}): ${await responseText(response)}`);
  }
  try {
    return await response.json();
  } catch {
    throw new Error(`أعادت خدمة ${service} استجابة غير صالحة بصيغة JSON.`);
  }
}

async function requestBinary(url: string, init: RequestInit, service: string) {
  console.info(`[Sard][API] ${service}: ${init.method || "GET"} ${url}`);
  let response: Response;
  try {
    response = await fetch(url, { ...init, signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS) });
  } catch (error) {
    throw new Error(`تعذر الاتصال بخدمة ${service}: ${error instanceof Error ? error.message : "خطأ شبكة غير معروف"}`);
  }
  if (!response.ok) throw new Error(`فشلت خدمة ${service} (${response.status}): ${await responseText(response)}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (!bytes.length) throw new Error(`أعادت خدمة ${service} ملفاً فارغاً.`);
  return { bytes, contentType: response.headers.get("content-type") || "application/octet-stream" };
}

function extractJsonSubstring(text: string): string {
  let stripped = text.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
  try {
    JSON.parse(stripped);
    return stripped;
  } catch {
    const firstBrace = stripped.search(/[\{\[]/);
    const lastBrace = Math.max(stripped.lastIndexOf("}"), stripped.lastIndexOf("]"));
    if (firstBrace !== -1 && lastBrace > firstBrace) {
      stripped = stripped.slice(firstBrace, lastBrace + 1);
    }
    try {
      JSON.parse(stripped);
      return stripped;
    } catch {
      const cleaned = stripped
        .replace(/("[\w-]+"\s*:\s*)\**\s*#*\s*\*+\s*"/g, '$1"')
        .replace(/("[\w-]+"\s*:\s*)\**\s*#*\s*\*+\s*/g, "$1")
        .replace(/\*\*/g, "")
        .replace(/###/g, "")
        .replace(/,\s*([\}\]])/g, "$1")
        .replace(/[\u0000-\u001F\u007F-\u009F]/g, (match) => (match === "\n" || match === "\r" || match === "\t" ? match : ""));

      try {
        JSON.parse(cleaned);
        return cleaned;
      } catch {
        return cleaned;
      }
    }
  }
}

function jsonFromModel(content: string, name: string): unknown {
  const target = extractJsonSubstring(content);
  try {
    return JSON.parse(target);
  } catch (error) {
    console.error(`[Sard][JSON Error] Raw output from ${name}:\n`, content.slice(0, 500));
    const details = error instanceof Error ? error.message : "خطأ تنسيق غیر معروف";
    throw new Error(`أعاد نموذج ${name} نصاً لا يطابق JSON المطلوب (${details}). لم يتم استخدام أي بديل.`);
  }
}

function modelMessageContent(payload: unknown) {
  const content = (payload as { choices?: Array<{ message?: { content?: unknown } }> }).choices?.[0]?.message?.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map((part) => typeof part === "string" ? part : "").join("");
  throw new Error("لم تُعد واجهة Hugging Face محتوى نصياً من نموذج Qwen.");
}

async function chatWithQwen(system: string, user: string, maxTokens: number) {
  const payload = await requestJson(
    env("HF_CHAT_ENDPOINT"),
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headersForHf(env("HF_API_TOKEN")) },
      body: JSON.stringify({
        model: env("HF_QWEN_MODEL"),
        messages: [{ role: "system", content: system }, { role: "user", content: user }],
        temperature: 0.45,
        max_tokens: Math.min(MAX_TEXT_COMPLETION_TOKENS, maxTokens),
      }),
    },
    `Qwen (${env("HF_QWEN_MODEL")})`,
  );
  return modelMessageContent(payload);
}

export function normalizeArabicTashkeel(text: string): string {
  if (!text) return "";
  return text
    // Fix reversed order: Vowel + Shaddah -> Shaddah + Vowel (e.g. َ ّ -> َّ )
    .replace(/([ًٌٍَُِّْ])(ّ)/g, "$2$1")
    // Collapse accidental duplicate diacritics on the same letter
    .replace(/([ًٌٍَُِّّْ])\1+/g, "$1")
    // Ensure clean spacing around Arabic punctuation for smooth TTS pauses
    .replace(/\s*([،,.!؟])\s*/g, "$1 ")
    .trim();
}

export function createSceneDurationPlan(totalDurationSeconds: number) {
  if (totalDurationSeconds < MIN_SCENE_DURATION_SECONDS) {
    throw new Error(`أقل مدة للقصة هي ${MIN_SCENE_DURATION_SECONDS} ثوانٍ.`);
  }
  if (totalDurationSeconds > MAX_SCENES_PER_STORY * MAX_SCENE_DURATION_SECONDS) {
    throw new Error(`المدة القصوى هي 80 ثانية (16 مشهداً × 5 ثوانٍ).`);
  }

  const sceneCount = Math.ceil(totalDurationSeconds / MAX_SCENE_DURATION_SECONDS);
  const baseDuration = Math.floor(totalDurationSeconds / sceneCount);
  const extraSeconds = totalDurationSeconds % sceneCount;
  return Array.from({ length: sceneCount }, (_, index) => baseDuration + (index < extraSeconds ? 1 : 0));
}

export function parseArabicDurationToSeconds(value: string) {
  const normalised = value
    .trim()
    .replace(/[٠-٩]/g, (digit) => "٠١٢٣٤٥٦٧٨٩".indexOf(digit).toString())
    .replace("،", ".");
  const match = normalised.match(/(\d+(?:\.\d+)?)/);
  if (!match) throw new Error("أدخل مدة تحتوي على رقم، مثل: 3 دقائق أو 45 ثانية.");
  const amount = Number(match[1]);
  if (!Number.isFinite(amount) || amount <= 0) throw new Error("مدة القصة يجب أن تكون أكبر من صفر.");
  const isMinutes = /دقيق|دقائ|minute|min/i.test(normalised);
  const isSeconds = /ثان|second|sec/i.test(normalised);
  if (!isMinutes && !isSeconds) throw new Error("اكتب وحدة المدة: دقائق أو ثوانٍ.");
  const seconds = Math.round(isMinutes ? amount * 60 : amount);
  if (seconds > MAX_SCENES_PER_STORY * MAX_SCENE_DURATION_SECONDS) throw new Error("المدة القصوى المتاحة هي دقيقة و20 ثانية.");
  return seconds;
}

function validateGeneratedScript(raw: unknown, durations: number[]): GeneratedScript {
  const script = generatedScriptSchema.parse(raw);
  if (script.scenes.length !== durations.length) {
    throw new Error(`أنشأ Qwen ${script.scenes.length} مشهداً بدل ${durations.length} مشهداً مطلوباً. لم يتم تعديل الناتج تلقائياً.`);
  }
  script.scenes.forEach((scene, index) => {
    if (scene.number !== index + 1 || scene.durationSeconds !== durations[index]) {
      throw new Error(`بيانات مدة أو رقم المشهد ${index + 1} من Qwen لا تطابق خطة المشاهد. لم يتم تعديل الناتج تلقائياً.`);
    }
  });
  return script;
}

function validateGeneratedPrompts(raw: unknown, sceneCount: number[]): GeneratedPrompts {
  const prompts = generatedPromptsSchema.parse(raw);
  if (prompts.prompts.length !== sceneCount.length) {
    throw new Error(`أنشأ Qwen ${prompts.prompts.length} مطالبة بصرية بدل ${sceneCount.length}. لم يتم تعديل الناتج تلقائياً.`);
  }
  prompts.prompts.forEach((prompt, index) => {
    if (prompt.number !== index + 1) throw new Error(`رقم مطالبة المشهد ${index + 1} غير صحيح.`);
  });
  return prompts;
}

function inputContext(input: StoryInput) {
  return `العنوان: ${input.title}\nفكرة القصة: ${input.topic}\nالمرحلة: ${input.stage}\nالعمر: ${input.age}\nالمستوى: ${input.level}\nالاحتياجات: ${input.needs}\nالأهداف: ${input.objectives.join(" | ")}\nالأسلوب: ${input.style}\nالنبرة: ${input.tone}\nجنس الراوي: ${input.speakerGender === "male" ? "ذكر" : "أنثى"}`;
}

function batches<T>(items: T[]) {
  return Array.from({ length: Math.ceil(items.length / SCENES_PER_QWEN_BATCH) }, (_, index) => items.slice(index * SCENES_PER_QWEN_BATCH, (index + 1) * SCENES_PER_QWEN_BATCH));
}

async function generateStoryFoundation(input: StoryInput) {
  const content = await chatWithQwen(
    "أنت سيناريست ومخرج تعليمي محترف مقتدر، متخصص في كتابة قصص واقعية، هادفة، وقوية باللغة العربية الفصحى المشرقة للأطفال والناشئة. اكتب بأسلوب سردي سينمائي متماسك، وتجنب الكلام السطحي أو الحشو العشوائي.\n\nتنبيه حاسم للخرجات: أعد JSON صالحاً فقط ومن دون Markdown. يمنع منعاً باتاً استخدام رموز التنسيق مثل ** أو ### أو * في أي مكان داخل قيم الـ JSON أو خارجها. اكتب القيم كنصوص صريحة ونظيفة فقط.\n\nقواعد السيناريو القوي والهادف:\n1. سياق واقعي وموقف حقيقي: ابدأ القصة بموقف أو مشكلة واقعية ملموسة من حياة الطفل (مثل: هدر المياه في المنزل، العناية بحديقة أو نبات، تجربة مدرسية، أو اكتشاف ظاهرة طبيعية).\n2. تحقيق تام ومباشر للأهداف التعليمية: يجب أن يُسهم كل جزء من القصة في تحقيق الأهداف التعليمية التالية بوضوح ملموس: (" + input.objectives.join(" | ") + ").\n3. بناء سببي متدرج (Cause-and-Effect Narrative Arc):\n   - المشكلة أو التساؤل المباشر: موقف يحفز التفكير والعمل.\n   - البحث والاكتشاف: حوار وتفاعل حقيقي يوضح الأسباب والنتائج ببساطة.\n   - الحل والتطبيق العملي: قرار ملهم وسلوك إيجابي ملموس.\n4. شخصيات واقعية ذات دافع: صف الشخصيات بأسماء واقعية، مظهر منظم، وملابس مناسبة للبيئة، ودافع واعي للتعلم والعمل.\n5. دليل نمط بصري سينمائي: رسوم ثلاثية الأبعاد فاخرة (Pixar/Disney 3D style) بألوان غنية وإضاءة سينمائية دافئة.",
    `${inputContext(input)}\n\nصغ أساس قصة تعليمية واقعية، قوية، ومحبوكة الهدف والحبكة.\nأعد: {"script":"ملخص وسيناريو القصة الشامل متضمناً المشكلة الحقيقية، الأسباب، والحل العملي الملموس","characters":[{"name":"اسم الشخصية","description":"وصف تفصيلي واقعي للشخصية والملابس والدوافع"}],"visualStyleGuide":"دليل النمط البصري والرسوم ثلاثية الأبعاد الإيجابية نصاً بالعربية"}`,
    6_000,
  );
  return storyFoundationSchema.parse(jsonFromModel(content, "Qwen"));
}

async function generateSceneBatch(input: StoryInput, foundation: z.infer<typeof storyFoundationSchema>, durations: number[], startNumber: number, onRetry?: (message: string) => Promise<void>) {
  const expected = durations.map((seconds, index) => `${startNumber + index}: ${seconds} ثوانٍ، نحو ${Math.max(5, Math.round(seconds * 2))} كلمة للنص الصوتي`).join("، ");
  let lastError: unknown;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const content = await chatWithQwen(
      "أنت سيناريست ورسّام مشاهد لقصص تعليمية عربية سينمائية فائقة الواقعية والجودة. اكتب بالعربية الفصحى المشرقة والمحبوكة، وأعد JSON صالحاً فقط ومن دون Markdown.\n\nقواعد المشاهد القصصية القوية والهادفة:\n1. لا حشو ولا إنشاء: تجنب الكلام السطحي أو العبارات المبتذلة؛ كل مشهد يجب أن يمثل خطوة حدثية حقيقية ومعلومة/سلوكاً ملموساً يخدم الأهداف التعليمية مباشرة: (" + input.objectives.join(" | ") + ").\n2. نص تعليق صوتي قوي وسلس (Narration): اكتب نصاً سردياً فصيحاً، غنياً بالأسباب والنتائج والمفردات التربوية والعملية، ومحسوب الكلمات بدقة يناسب مدة المشهد المحددة.\n3. وصف بصري واقعي سينمائي (Visual Description): صف تفاصيل حركة الشخصيات، التعبيرات، الأثاث، البيئة الواقعية، والإضاءة بوضوح سينمائي فائق.\n4. المنطق الفيزيائي والواقعية: البشر يقفون ويتفاعلون بشكل طبيعي على الأرض بجانب الأثاث والبيئة الواقعية (يمنع الوضعيات السريالية أو البشر المصغرون داخل الأحواض).",
      `${inputContext(input)}\n\nأساس القصة: ${foundation.script}\nالشخصيات: ${JSON.stringify(foundation.characters)}\nدليل النمط: ${foundation.visualStyleGuide}\n\nالمشاهد المطلوبة حصراً: ${expected}\n\nأعد: {"scenes":[{"number":${startNumber},"title":"عنوان المشهد","durationSeconds":${durations[0]},"narration":"النص الصوتي السردي القوي والمركز","visualDescription":"الوصف البصري السينمائي الواقعي والمستقر فيزياء"}]}`,
      9_000,
    );
    try {
      const batch = generatedSceneBatchSchema.parse(jsonFromModel(content, "Qwen"));
      if (batch.scenes.length !== durations.length) throw new Error(`أنشأ Qwen ${batch.scenes.length} مشهداً في الدفعة بدل ${durations.length}.`);
      batch.scenes.forEach((scene, index) => {
        if (scene.number !== startNumber + index || scene.durationSeconds !== durations[index]) throw new Error(`بيانات المشهد ${startNumber + index} لا تطابق رقم الدفعة أو مدتها.`);
      });
      return batch.scenes;
    } catch (error) {
      lastError = error;
      if (attempt === 3) break;
      const message = `دفعة مشاهد Qwen التي تبدأ بالمشهد ${startNumber} غير مكتملة (${error instanceof Error ? error.message : "خطأ تحقق"}). تتم إعادة المحاولة (${attempt + 1}/3).`;
      console.warn(`[Sard][Qwen] ${message}`);
      await onRetry?.(message);
    }
  }
  throw lastError;
}

async function generateScript(input: StoryInput, durations: number[], onRetry?: (message: string) => Promise<void>) {
  const foundation = await generateStoryFoundation(input);
  const scenes: z.infer<typeof generatedSceneSchema>[] = [];
  for (const [batchIndex, durationBatch] of batches(durations).entries()) {
    scenes.push(...await generateSceneBatch(input, foundation, durationBatch, batchIndex * SCENES_PER_QWEN_BATCH + 1, onRetry));
  }
  return validateGeneratedScript({ ...foundation, scenes }, durations);
}

async function vocalizeNarrations(scenes: StoryScene[], onRetry?: (message: string) => Promise<void>) {
  const vocalized: Array<Pick<StoryScene, "number" | "narration">> = [];
  for (const sceneBatch of batches(scenes)) {
    const source = sceneBatch.map(({ number, narration }) => ({ number, narration }));
    let batchResult: Array<Pick<StoryScene, "number" | "narration">> | null = null;
    for (let attempt = 1; attempt <= 2; attempt += 1) {
      try {
        const content = await chatWithQwen(
          "أنت مدقّق لغوي خبير ومتخصص في التشكيل العربي الكامل والدقيق المخصص لأنظمة النطق الآلي (Text-to-Speech). أعد JSON صالحاً فقط ومن دون Markdown.\n\nالقواعد الذهبية للتشكيل الصوتي المتقن:\n1. التشكيل التام والدقيق: ضع التشكيل الكامل (الفتحة، الضمة، الكسرة، السكون، الشدة مع حركتها، والتنوين) على كل حرف في النص دون استثناء لمنع أي لبس أو نطق خاطئ من الذكاء الاصطناعي (مثل: قَطْرَةُ نَدَى، الحَنَفِيَّةُ، البُخَارُ، التَّرْشِيدُ، شَمْسٍ).\n2. الوقف والابتداء عند الترقيم: ضع سكوناً على الحرف الأخير قبل علامات الترقيم (، . ! ؟) أو اترك حركته ساكنة لضمان وقوف صوتي طبيعي ومريح للراوي.\n3. دمج الشدة بالحركات: الشدة يجب أن ترافق الفتحة أو الضمة أو الكسرة دائماً (شَّ، شُّ، شِّ).\n4. عدم التغيير: لا تغير الكلمات أو المعنى أو الألفاظ أو علامات الترقيم مطلقاً.",
          `النصوص المطلوب تشكيلها: ${JSON.stringify(source)}\n\nأعد: {"scenes":[{"number":${sceneBatch[0].number},"narration":"نص عربي مشكّل تشكيلاً كاملاً ودقيقاً للنطق الصوتي"}]}`,
          9_000,
        );
        const result = vocalizedNarrationsSchema.parse(jsonFromModel(content, "Qwen"));
        if (result.scenes.length !== sceneBatch.length) throw new Error(`أعاد Qwen ${result.scenes.length} نصوصاً مشكّلة بدلاً من ${sceneBatch.length}.`);
        result.scenes.forEach((scene, index) => {
          if (scene.number !== sceneBatch[index].number) throw new Error(`رقم النص المشكّل للمشهد ${sceneBatch[index].number} غير صحيح.`);
          scene.narration = normalizeArabicTashkeel(scene.narration);
        });
        batchResult = result.scenes;
        break;
      } catch (error) {
        const message = `تعذر تشكيل دفعة المشاهد التي تبدأ بالمشهد ${sceneBatch[0].number} (${error instanceof Error ? error.message : "خطأ تحقق"}). تتم إعادة المحاولة.`;
        console.warn(`[Sard][Qwen] ${message}`);
        await onRetry?.(message);
      }
    }
    if (batchResult) {
      vocalized.push(...batchResult);
    } else {
      console.warn(`[Sard][Qwen] تعذر تشكيل الدفعة التي تبدأ بالمشهد ${sceneBatch[0].number}، وسيتم اعتماد النص الأصلي.`);
      vocalized.push(...source);
    }
  }
  return vocalized;
}

async function generateVisualPrompts(script: GeneratedScript, onRetry?: (message: string) => Promise<void>) {
  const prompts: z.infer<typeof generatedPromptSchema>[] = [];
  for (const sceneBatch of batches(script.scenes)) {
    const sceneSummary = sceneBatch.map((scene) => ({
      number: scene.number,
      title: scene.title,
      visualDescription: scene.visualDescription,
      durationSeconds: scene.durationSeconds,
      videoDirection: "Clean 3D Pixar/Disney character animation: one main focal character action, smooth fluid physics, clean uncluttered backdrop, studio lighting, stable identity. Strictly no morphing, no floating text, no random objects, no background clutter.",
    }));
    const content = await chatWithQwen(
      "أنت مخرج فني خبير للرسوم المتحركة ثلاثية الأبعاد (Pixar/Disney style). أعد JSON صالحاً فقط ومن دون Markdown. حافظ على الاتساق التام للشخصيات.\nقواعد التناسب والواقعية البصرية والتكوين النظيف:\n1. التناسب والموقع المنطقي: البشري يقف على الأرض بحجمه المنطقي بجانب الأثاث، ويمنع منعاً باتاً جعل الإنسان يظهر بحجم مصغر داخل حوض الغسيل أو العلب أو الوضعيات المنافية للمنطق.\n2. التكوين النظيف المباشر: اجعل المشهد مركزاً وواضحاً وسهل الفهم للأطفال بدون أي عناصر عشوائية أو نصوص floating text أو شعارات.\n3. أعد imagePrompt بالعربية الفصحى المباشرة للعرض.\n4. أعد imageGenerationPrompt بالإنجليزية فقط، ومطالبة FLUX احترافية تصف الشخصية في موضعها الفيزيائي الطبيعي، والخلفية البسيطة النظيفة، والإضاءة الناعمة، مع منع أي وضعيات غريبة أو نصوص.\n5. أعد videoPrompt بالإنجليزية فقط، حركية دقيقة وطبيعية للشخصيات بدون اهتزاز أو وضعيات شاذة.",
      `دليل النمط الثابت: ${script.visualStyleGuide}\nالشخصيات: ${JSON.stringify(script.characters)}\nالمشاهد في هذه الدفعة: ${JSON.stringify(sceneSummary)}\n\nلكل مشهد أنشئ:\n1. imagePrompt: وصف عربي واضح ومباشر بموقع فيزيائي منطقي.\n2. imageGenerationPrompt: Clean, realistic placement English FLUX prompt, human character standing naturally on floor, 3D Pixar style render, strictly no human inside sink bowl, no floating text, no extra random objects.\n3. videoPrompt: Smooth natural movement English Wan I2V motion prompt.\n\nأعد: {"prompts":[{"number":${sceneBatch[0].number},"imagePrompt":"وصف عربي بموقع منطقي","imageGenerationPrompt":"Clean realistic positioning English FLUX prompt","videoPrompt":"Smooth clear English Wan I2V motion prompt"}]}`,
      9_000,
    );
    let batch: GeneratedPrompts;
    try {
      batch = generatedPromptsSchema.parse(jsonFromModel(content, "Qwen"));
    } catch (error) {
      const message = `دفعة مطالبات Qwen التي تبدأ بالمشهد ${sceneBatch[0].number} لا تطابق البنية المطلوبة (${error instanceof Error ? error.message : "خطأ تحقق"}). تتم إعادة طلب الدفعة نفسها من النموذج.`;
      console.warn(`[Sard][Qwen] ${message}`);
      await onRetry?.(message);
      const retryContent = await chatWithQwen(
        "أنت مخرج فني خبير للرسوم المتحركة ثلاثية الأبعاد. أعد JSON صالحاً فقط ومن دون Markdown. يجب أن يحتوي كل عنصر في prompts دائماً على number وimagePrompt وimageGenerationPrompt وvideoPrompt. اجعل المطالبات الإنجليزية ناصعة وواضحة ومركّزة على الشخصية الرئيسية بدون أي عناصر جانبية أو نصوص عشوائية.",
        `أعد إنشاء مطالبات هذه المشاهد فقط: ${JSON.stringify(sceneSummary)}\n\nأعد جميع العناصر ولا تحذف أي حقل. الصيغة الإلزامية: {"prompts":[{"number":${sceneBatch[0].number},"imagePrompt":"وصف الصورة بالعربية","imageGenerationPrompt":"Clean detailed English FLUX prompt","videoPrompt":"Smooth clear English Wan I2V motion prompt"}]}`,
        9_000,
      );
      batch = generatedPromptsSchema.parse(jsonFromModel(retryContent, "Qwen"));
    }
    if (batch.prompts.length !== sceneBatch.length) throw new Error(`أنشأ Qwen ${batch.prompts.length} مطالبة بصرية في دفعة بدل ${sceneBatch.length}.`);
    batch.prompts.forEach((prompt, index) => {
      if (prompt.number !== sceneBatch[index].number) throw new Error(`رقم مطالبة المشهد ${sceneBatch[index].number} غير صحيح.`);
    });
    prompts.push(...batch.prompts);
  }
  return validateGeneratedPrompts({ prompts }, script.scenes.map((scene) => scene.number));
}

function resolveGradioMediaUrl(spaceUrl: string, media: string) {
  if (/^https?:\/\//.test(media)) return media;
  if (media.startsWith("/gradio_api/")) return `${spaceUrl}${media}`;
  return `${spaceUrl}/gradio_api/file=${media.startsWith("/") ? media.slice(1) : media}`;
}

function hasMediaUrl(value: unknown): boolean {
  if (typeof value === "string") return true;
  if (!value || typeof value !== "object") return false;
  const candidate = value as { path?: unknown; url?: unknown };
  return typeof candidate.url === "string" || typeof candidate.path === "string";
}

function extractGeneratedImageUrl(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const items = Array.isArray(data) ? data : [data];
  const firstItem = items.find((item) => hasMediaUrl(item)) ?? items[0];
  if (typeof firstItem === "string") return firstItem;
  if (!firstItem || typeof firstItem !== "object") return null;
  const candidate = firstItem as { path?: unknown; url?: unknown };
  if (typeof candidate.url === "string") return candidate.url;
  if (typeof candidate.path === "string") return candidate.path;
  return null;
}

function extractGeneratedMediaUrl(result: unknown): string | null {
  if (!result || typeof result !== "object") return null;
  const data = "data" in result ? (result as { data?: unknown }).data : result;
  const firstItem = Array.isArray(data) ? data.find((item) => hasMediaUrl(item)) ?? data[0] : data;
  if (typeof firstItem === "string") return firstItem;
  if (!firstItem || typeof firstItem !== "object") return null;
  const candidate = firstItem as { path?: unknown; url?: unknown };
  if (typeof candidate.url === "string") return candidate.url;
  if (typeof candidate.path === "string") return candidate.path;
  return null;
}

const BLANK_CANVAS_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
const BLANK_CANVAS_BLOB = new Blob([Buffer.from(BLANK_CANVAS_PNG, "base64")], { type: "image/png" });

async function generateImage(prompt: string, onRetry?: (message: string) => Promise<void>, retryStaggerMs = 0) {
  let lastError: unknown;
  const spaceId = env("HF_IMAGE_SPACE_ID", FLUX_ADVERTISEMENT_SPACE);
  const spaceUrl = env("HF_IMAGE_SPACE_URL", FLUX_ADVERTISEMENT_SPACE_URL);

  const cleanPrompt = prompt.trim();
  const professionalPrompt = `${cleanPrompt}, realistic human proportions and natural physical scale, human character standing naturally on floor, clean simple focused composition, 3D Pixar Disney style animation render, clear main subject, uncluttered minimal background, soft studio lighting, high resolution, no surreal positioning, no human standing inside sink bowl, no miniature human inside basin, no clipping, no floating text, no speech bubbles, no watermark, no blur`;

  for (let attempt = 1; attempt <= MAX_FLUX_ATTEMPTS; attempt += 1) {
    let client: Awaited<ReturnType<typeof Client.connect>> | undefined;
    try {
      console.info(`[Sard][API] توليد الصورة عبر Hugging Face Space: ${spaceId}`);
      const token = env("HF_API_TOKEN");
      client = await Client.connect(
        spaceId,
        token.startsWith("hf_") ? { token: token as `hf_${string}` } : undefined,
      );

      const rawResult = await client.predict("/infer", {
        guidance_scale: 1,
        input_images: [{ image: handle_file(BLANK_CANVAS_BLOB) }],
        prompt: professionalPrompt,
        randomize_seed: true,
        seed: 0,
        steps: 4,
        style_name: "None",
      });

      const mediaUrl = extractGeneratedImageUrl(rawResult.data);
      if (!mediaUrl) {
        throw new Error("أعادت مساحة FLUX استجابة بدون رابط صورة صالح.");
      }

      const fullUrl = resolveGradioMediaUrl(spaceUrl, mediaUrl);
      return await requestBinary(fullUrl, { headers: headersForHf(token) }, `تنزيل صورة FLUX (${spaceId})`);
    } catch (error) {
      lastError = error;
      const details = formatErrorMessage(error);
      const isTemporaryImageProviderFailure = /Please upload at least one image|ZeroGPU worker error|AcceleratorError|Connection errored out|Could not resolve app config|Could not parse server response|Traceback|queue\/data|Internal Server Error|fetch failed|network error|\b429\b|\b50[0-4]\b|temporar|unavailable|overloaded/i.test(details);
      if (!isTemporaryImageProviderFailure || attempt === MAX_FLUX_ATTEMPTS) throw new Error(details);
      const nextAttempt = attempt + 1;
      const message = `تعذّرت مساحة توليد الصور مؤقتاً (${safeProviderText(details)}). تتم إعادة محاولة المشهد نفسه عبر مساحة ${spaceId} (${nextAttempt}/${MAX_FLUX_ATTEMPTS}) بعد انتظار قصير.`;
      console.warn(`[Sard][Images] ${message}`);
      await onRetry?.(message);
      await new Promise<void>((resolve) => setTimeout(resolve, attempt * 12_000 + retryStaggerMs));
    } finally {
      if (client?.heartbeat_event) {
        client.heartbeat_event.onerror = null;
        client.heartbeat_event.close();
      }
    }
  }
  throw new Error(formatErrorMessage(lastError));
}

function gradioApiName(endpoint: string) {
  if (endpoint.startsWith("/")) return endpoint;
  const name = endpoint.split("/gradio_api/call/")[1];
  if (!name) return "/predict";
  return `/${name}`;
}

async function generateSpeech(text: string, gender: SpeakerGender, rate: number) {
  const token = env("HF_API_TOKEN");
  const spaceId = env("HF_TTS_SPACE_ID");
  const spaceUrl = env("HF_TTS_SPACE_URL");
  const cleanText = normalizeArabicTashkeel(text);
  let client: Awaited<ReturnType<typeof Client.connect>> | undefined;
  try {
    client = await Client.connect(spaceId, token.startsWith("hf_") ? { token: token as `hf_${string}` } : undefined);
    const result = await client.predict(gradioApiName(env("HF_TTS_ENDPOINT")), {
      text: cleanText,
      voice: gender === "male" ? env("HF_TTS_MALE_VOICE") : env("HF_TTS_FEMALE_VOICE"),
      rate,
      pitch: 0,
    });
    const media = extractGeneratedMediaUrl(result.data);
    if (!media) throw new Error("لم تُعد مساحة innoai Edge TTS رابط الملف الصوتي الناتج.");
    return requestBinary(
      resolveGradioMediaUrl(spaceUrl, media),
      { headers: headersForHf(token) },
      "تنزيل صوت innoai Edge TTS",
    );
  } finally {
    if (client?.heartbeat_event) {
      client.heartbeat_event.onerror = null;
      client.heartbeat_event.close();
    }
  }
}

async function generateVideo(imageUrl: string, prompt: string, durationSeconds: number, onRetry?: (message: string) => Promise<void>) {
  const spaceId = env("HF_VIDEO_SPACE_ID", WAN_I2V_VIDEO_SPACE);
  const spaceUrl = env("HF_VIDEO_SPACE_URL", WAN_I2V_VIDEO_SPACE_URL);
  const token = env("HF_API_TOKEN");
  const requestedDuration = Math.max(3, Math.min(5, durationSeconds));

  const cleanPrompt = prompt.trim();
  const professionalVideoPrompt = cleanPrompt.toLowerCase().includes("motion") || cleanPrompt.toLowerCase().includes("animation")
    ? cleanPrompt
    : `${cleanPrompt}, high quality continuous 3D character motion, fluid physical animation, stable identity, cinematic camera movement, smooth 60fps action, crisp 3D render, no static posture, no flickering, no warping, no sudden morphing, no text, no watermark`;

  console.info(`[Sard][API] تنزيل صورة المشهد لتمريرها إلى مساحة Wan I2V: ${imageUrl}`);
  const imageRes = await fetch(imageUrl);
  if (!imageRes.ok) throw new Error(`تعذّر تنزيل صورة المشهد لتوليد الفيديو (${imageRes.status}).`);
  const imageBlob = await imageRes.blob();

  let lastError: unknown;
  for (let attempt = 1; attempt <= MAX_WAN_ATTEMPTS; attempt += 1) {
    let client: Awaited<ReturnType<typeof Client.connect>> | undefined;
    try {
      console.info(`[Sard][API] Wan I2V: إنشاء فيديو للمشهد عبر مساحة ${spaceId} (محاولة ${attempt}/${MAX_WAN_ATTEMPTS}).`);
      client = await Client.connect(
        spaceId,
        token.startsWith("hf_") ? { token: token as `hf_${string}` } : undefined,
      );

      const rawResult = await client.predict("/generate_video", {
        duration_seconds: requestedDuration,
        guidance_scale: 1,
        guidance_scale_2: 1,
        input_image: handle_file(imageBlob),
        negative_prompt:
          "static image, no motion, low quality, distorted product, warped logo, blurry, flicker, artifacts, extra objects, unreadable text, watermark, subtitles, text overlay",
        prompt: professionalVideoPrompt,
        randomize_seed: true,
        seed: 42,
        steps: 6,
      });

      const mediaUrl = extractGeneratedMediaUrl(rawResult);
      if (!mediaUrl) {
        throw new Error("أعادت مساحة Wan I2V استجابة بدون رابط فيديو صالح.");
      }

      const fullUrl = resolveGradioMediaUrl(spaceUrl, mediaUrl);
      return await requestBinary(fullUrl, { headers: headersForHf(token) }, `تنزيل فيديو Wan I2V (${spaceId})`);
    } catch (error) {
      lastError = error;
      const details = formatErrorMessage(error);
      const isTemporaryVideoProviderFailure = /ZeroGPU worker error|AcceleratorError|Connection errored out|Could not resolve app config|Could not parse server response|Traceback|queue\/data|Internal Server Error|fetch failed|network error|\b429\b|\b50[0-4]\b|temporar|unavailable|overloaded/i.test(details);
      if (!isTemporaryVideoProviderFailure || attempt === MAX_WAN_ATTEMPTS) throw new Error(details);
      const nextAttempt = attempt + 1;
      const message = `تعذّرت مساحة توليد الفيديو Wan I2V مؤقتاً (${safeProviderText(details)}). تتم إعادة المحاولة (${nextAttempt}/${MAX_WAN_ATTEMPTS}) بعد انتظار قصير.`;
      console.warn(`[Sard][Videos] ${message}`);
      await onRetry?.(message);
      await new Promise<void>((resolve) => setTimeout(resolve, attempt * 5_000));
    } finally {
      if (client?.heartbeat_event) {
        client.heartbeat_event.onerror = null;
        client.heartbeat_event.close();
      }
    }
  }
  throw new Error(formatErrorMessage(lastError));
}

function extensionFor(contentType: string, fallback: string) {
  const type = contentType.toLowerCase();
  if (type.includes("png")) return "png";
  if (type.includes("webp")) return "webp";
  if (type.includes("jpeg") || type.includes("jpg")) return "jpg";
  if (type.includes("wav")) return "wav";
  if (type.includes("ogg")) return "ogg";
  if (type.includes("mp4")) return "mp4";
  if (type.includes("mpeg") || type.includes("mp3")) return "mp3";
  return fallback;
}

async function uploadToImageKit(bytes: Buffer, fileName: string, folder: string, contentType: string) {
  console.info(`[Sard][API] ImageKit: رفع ${fileName}`);
  const form = new FormData();
  form.append("file", new Blob([new Uint8Array(bytes)], { type: contentType }), fileName);
  form.append("fileName", fileName);
  form.append("folder", folder);
  form.append("useUniqueFileName", "true");
  const basic = Buffer.from(`${env("IMAGEKIT_PRIVATE_KEY")}:`).toString("base64");
  const response = await fetch("https://upload.imagekit.io/api/v1/files/upload", {
    method: "POST",
    headers: { Authorization: `Basic ${basic}` },
    body: form,
    signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
  });
  if (!response.ok) throw new Error(`فشل رفع ImageKit (${response.status}): ${await responseText(response)}`);
  const payload = await response.json() as { url?: unknown };
  if (typeof payload.url !== "string") throw new Error("لم يُعد ImageKit رابط الملف بعد الرفع.");
  return payload.url;
}

function runFfmpeg(args: string[]) {
  const binary = ffmpegPath;
  if (!binary) throw new Error("ملف ffmpeg-static غير متاح؛ لا يمكن دمج أو تقليم الوسائط.");
  console.info(`[Sard][FFmpeg] ${args.join(" ")}`);
  return new Promise<void>((resolve, reject) => {
    const process = spawn(binary, args, { windowsHide: true, stdio: ["ignore", "ignore", "pipe"] }) as unknown as {
      stderr: { on(event: "data", listener: (chunk: Buffer) => void): void };
      once(event: "error", listener: (error: Error) => void): void;
      once(event: "close", listener: (code: number | null) => void): void;
    };
    let stderr = "";
    process.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
    process.once("error", reject);
    process.once("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`فشل FFmpeg (رمز ${code}): ${stderr.slice(-1_000)}`));
    });
  });
}

async function readMediaDuration(source: string) {
  const binary = ffmpegPath;
  if (!binary) throw new Error("ملف ffmpeg-static غير متاح؛ لا يمكن قياس مدة الصوت.");
  return new Promise<number>((resolve, reject) => {
    const process = spawn(binary, ["-hide_banner", "-i", source], { windowsHide: true, stdio: ["ignore", "ignore", "pipe"] }) as unknown as {
      stderr: { on(event: "data", listener: (chunk: Buffer) => void): void };
      once(event: "error", listener: (error: Error) => void): void;
      once(event: "close", listener: (code: number | null) => void): void;
    };
    let stderr = "";
    process.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
    process.once("error", reject);
    process.once("close", () => {
      const match = stderr.match(/Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)/);
      if (!match) return reject(new Error("تعذر قراءة مدة ملف الصوت الذي أعادته مساحة TTS."));
      resolve(Number(match[1]) * 3_600 + Number(match[2]) * 60 + Number(match[3]));
    });
  });
}

function arabicWordCount(text: string) {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

async function rewriteNarrationForDuration(text: string, targetDurationSeconds: number, actualDurationSeconds: number) {
  const targetWordCount = Math.max(4, Math.round(arabicWordCount(text) * targetDurationSeconds / actualDurationSeconds));
  const content = await chatWithQwen(
    "أنت محرر نصوص عربية متخصص في التعليق الصوتي. أعد JSON صالحاً فقط ومن دون Markdown. أعد narration عربياً فصيحاً مشكّلاً بالكامل تشكيلاً دقيقاً للحروف (بالفتحة، الضمة، الكسرة، السكون، الشدة مع حركتها، والتنوين) لضمان النطق الصحيح من الذكاء الاصطناعي. اختصر النص أو وسّعه مع الحفاظ التام على الحدث والمعنى والشخصيات.",
    `النص الحالي: ${text}\nمدة الصوت الفعلية: ${actualDurationSeconds.toFixed(2)} ثانية\nالمدة المطلوبة: ${targetDurationSeconds} ثوانٍ\nعدد الكلمات التقريبي المطلوب: ${targetWordCount}\n\nأعد: {"narration":"نص عربي مشكّل تشكيلاً كاملاً للنطق الصوتي"}`,
    1_500,
  );
  const narration = durationMatchedNarrationSchema.parse(jsonFromModel(content, "Qwen")).narration;
  return normalizeArabicTashkeel(narration);
}

async function alignAudioDuration(filePath: string, targetDurationSeconds: number) {
  const actualDuration = await readMediaDuration(filePath);
  const diff = Math.abs(actualDuration - targetDurationSeconds);
  if (diff <= 0.05) return;

  const ratio = actualDuration / targetDurationSeconds;
  const tempo = Math.max(0.5, Math.min(2.0, ratio));
  console.info(`[Sard][FFmpeg] محاذاة مدة التعليق الصوتي من ${actualDuration.toFixed(2)}s إلى ${targetDurationSeconds}s (tempo=${tempo.toFixed(3)})`);
  const tempPath = `${filePath}.aligned.mp3`;
  await runFfmpeg([
    "-y", "-i", filePath,
    "-filter:a", `atempo=${tempo.toFixed(4)}`,
    "-c:a", "libmp3lame", "-b:a", "128k",
    tempPath,
  ]);
  const bytes = await readFile(tempPath);
  await writeFile(filePath, bytes);
  await unlink(tempPath).catch(() => undefined);
}

async function generateSpeechForDuration(text: string, gender: SpeakerGender, targetDurationSeconds: number, destination: string) {
  let narration = text;
  let rate = 0;
  let lastAudio: { bytes: Buffer; contentType: string } | undefined;

  for (let attempt = 1; attempt <= MAX_TTS_ATTEMPTS; attempt += 1) {
    const audio = await generateSpeech(narration, gender, rate);
    lastAudio = audio;
    await writeFile(destination, audio.bytes);
    const actualDuration = await readMediaDuration(destination);

    if (Math.abs(actualDuration - targetDurationSeconds) <= AUDIO_DURATION_TOLERANCE_SECONDS) {
      return { audio, narration };
    }

    const nextRate = Math.max(-50, Math.min(50, Math.round(((1 + rate / 100) * actualDuration / targetDurationSeconds - 1) * 100)));
    if (attempt === MAX_TTS_ATTEMPTS) break;

    if (nextRate !== rate && Math.abs(nextRate) <= 35) {
      console.info(`[Sard][TTS] إعادة توليد الصوت بمعدل ${nextRate}% لمطابقة مدة ${targetDurationSeconds} ثوانٍ.`);
      rate = nextRate;
      continue;
    }

    narration = await rewriteNarrationForDuration(narration, targetDurationSeconds, actualDuration);
    rate = 0;
    console.info(`[Sard][TTS] إعادة صياغة النص العربي المشكّل لتوليد صوت يطابق ${targetDurationSeconds} ثوانٍ.`);
  }

  await alignAudioDuration(destination, targetDurationSeconds);
  const finalBytes = await readFile(destination);
  return { audio: lastAudio ?? { bytes: finalBytes, contentType: "audio/mpeg" }, narration };
}

async function trimVideo(source: string, destination: string, durationSeconds: number) {
  await runFfmpeg([
    "-y", "-stream_loop", "-1", "-i", source, "-t", String(durationSeconds), "-an", "-vf",
    "fps=24,scale=768:512:force_original_aspect_ratio=decrease,pad=768:512:(ow-iw)/2:(oh-ih)/2",
    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", destination,
  ]);
}

async function concatenate(paths: string[], destination: string, kind: "audio" | "video", directory: string, durationSeconds?: number) {
  if (!paths.length) throw new Error("لا توجد ملفات لدمجها.");
  const listPath = join(directory, `${kind}-concat.txt`);
  const contents = paths.map((path) => `file '${path.replace(/'/g, "'\\\\''")}'`).join("\n");
  await writeFile(listPath, contents, "utf8");
  const durationArgs = durationSeconds ? ["-t", String(durationSeconds)] : [];
  const args = kind === "audio"
    ? ["-y", "-f", "concat", "-safe", "0", "-i", listPath, "-vn", ...durationArgs, "-c:a", "libmp3lame", "-b:a", "128k", destination]
    : ["-y", "-f", "concat", "-safe", "0", "-i", listPath, "-an", ...durationArgs, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", destination];
  await runFfmpeg(args);
}

async function mergeVideoWithAudio(video: string, audio: string, destination: string) {
  await runFfmpeg([
    "-y", "-i", video, "-i", audio,
    "-map", "0:v:0", "-map", "1:a:0",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", destination,
  ]);
}

function sceneProgress(start: number, end: number, position: number, total: number) {
  return Math.round(start + ((position - 1) / total) * (end - start));
}

function scenePairs<T>(items: T[]) {
  return Array.from({ length: Math.ceil(items.length / CONCURRENT_SCENE_GENERATIONS) }, (_, index) => items.slice(index * CONCURRENT_SCENE_GENERATIONS, (index + 1) * CONCURRENT_SCENE_GENERATIONS));
}

async function logAndProgress(id: string, progress: number, message: string) {
  await updateStoryProgress(id, progress, message);
  await appendStoryLog(id, { level: "info", message });
}

function storedScriptForResume(story: Awaited<ReturnType<typeof getStoryForUser>>, durations: number[]): GeneratedScript | undefined {
  if (!story?.script || !story.characters || !story.visualStyleGuide || story.scenes.length !== durations.length) return undefined;
  try {
    return validateGeneratedScript({
      script: story.script,
      characters: story.characters,
      visualStyleGuide: story.visualStyleGuide,
      scenes: story.scenes.map(({ number, title, durationSeconds, narration, visualDescription }) => ({ number, title, durationSeconds, narration, visualDescription })),
    }, durations);
  } catch {
    return undefined;
  }
}

export async function rebuildStoryVideoToRequestedDuration(storyId: string, userId: string) {
  let temporaryDirectory: string | undefined;
  try {
    const story = await getStoryForUser(storyId, userId);
    if (!story) throw new Error("لا يمكن إصلاح الفيديو لأن القصة غير موجودة أو لا تخص هذا المستخدم.");
    if (story.status !== "completed") throw new Error("لا يمكن إصلاح مدة الفيديو قبل اكتمال توليد القصة.");
    if (!story.scenes.length || story.scenes.some((scene) => !scene.videoUrl || !scene.audioUrl)) {
      throw new Error("لا يمكن إصلاح المدة لأن بعض فيديوهات أو أصوات المشاهد غير متاحة.");
    }

    temporaryDirectory = await mkdtemp(join(tmpdir(), `sard-video-${storyId.slice(0, 8)}-`));
    const storyFolder = `/sard-ai/${storyId}`;
    const videoPaths = new Map<number, string>();
    await appendStoryLog(storyId, { level: "info", message: "إعادة ضبط مدة فيديوهات المشاهد لتطابق مدة القصة المطلوبة." });

    for (const pair of scenePairs(story.scenes)) {
      await Promise.all(pair.map(async (scene) => {
        const video = await requestBinary(scene.videoUrl!, {}, `تنزيل فيديو المشهد ${scene.number} من ImageKit`);
        const source = join(temporaryDirectory!, `scene-${scene.number}-video-source.${extensionFor(video.contentType, "mp4")}`);
        const normalised = join(temporaryDirectory!, `scene-${scene.number}-video.mp4`);
        await writeFile(source, video.bytes);
        await trimVideo(source, normalised, scene.durationSeconds);
        const normalisedBytes = await readFile(normalised);
        const videoUrl = await uploadToImageKit(normalisedBytes, `scene-${scene.number}-video-${Date.now()}.mp4`, `${storyFolder}/videos`, "video/mp4");
        await saveSceneAsset(storyId, scene.number, "videoUrl", videoUrl);
        videoPaths.set(scene.number, normalised);
      }));
    }

    const combinedVideo = join(temporaryDirectory, "story-video.mp4");
    const orderedVideoPaths = story.scenes.map((scene) => videoPaths.get(scene.number));
    if (orderedVideoPaths.some((path) => !path)) throw new Error("تعذر العثور على أحد فيديوهات المشاهد بعد إصلاح مدتها.");
    await concatenate(orderedVideoPaths as string[], combinedVideo, "video", temporaryDirectory, story.totalDurationSeconds);
    const combinedVideoUrl = await uploadToImageKit(await readFile(combinedVideo), `story-video-${Date.now()}.mp4`, `${storyFolder}/final`, "video/mp4");
    const audioPaths = new Map<number, string>();
    for (const pair of scenePairs(story.scenes)) {
      await Promise.all(pair.map(async (scene) => {
        const normalised = join(temporaryDirectory!, `scene-${scene.number}-voice.mp3`);
        const generatedSpeech = await generateSpeechForDuration(scene.narration, story.input.speakerGender, scene.durationSeconds, normalised);
        if (generatedSpeech.narration !== scene.narration) await saveSceneNarration(storyId, scene.number, generatedSpeech.narration);
        const audioUrl = await uploadToImageKit(await readFile(normalised), `scene-${scene.number}-voice-${Date.now()}.mp3`, `${storyFolder}/audio`, "audio/mpeg");
        await saveSceneAsset(storyId, scene.number, "audioUrl", audioUrl);
        audioPaths.set(scene.number, normalised);
      }));
    }
    const combinedAudio = join(temporaryDirectory, "story-voice.mp3");
    const orderedAudioPaths = story.scenes.map((scene) => audioPaths.get(scene.number));
    if (orderedAudioPaths.some((path) => !path)) throw new Error("تعذر العثور على أحد أصوات المشاهد بعد إصلاح مدتها.");
    await concatenate(orderedAudioPaths as string[], combinedAudio, "audio", temporaryDirectory);
    const combinedAudioUrl = await uploadToImageKit(await readFile(combinedAudio), `story-voice-${Date.now()}.mp3`, `${storyFolder}/final`, "audio/mpeg");
    const narratedVideo = join(temporaryDirectory, "story-narrated-video.mp4");
    await mergeVideoWithAudio(combinedVideo, combinedAudio, narratedVideo);
    const combinedNarratedVideoUrl = await uploadToImageKit(await readFile(narratedVideo), `story-narrated-video-${Date.now()}.mp4`, `${storyFolder}/final`, "video/mp4");
    await completeStory(storyId, { ...story.assets, combinedAudioUrl, combinedVideoUrl, combinedNarratedVideoUrl });
    await appendStoryLog(storyId, { level: "info", message: `اكتمل إصلاح مدة الصوت والفيديو إلى ${story.totalDurationSeconds} ثانية ورفع النسخ الجديدة إلى ImageKit.` });
  } catch (error) {
    const message = error instanceof Error ? safeProviderText(error.message) : "حدث خطأ غير معروف أثناء إصلاح مدة الفيديو.";
    await appendStoryLog(storyId, { level: "error", message: `فشل إصلاح مدة الفيديو: ${message}` }).catch(() => undefined);
    throw error;
  } finally {
    if (temporaryDirectory) await rm(temporaryDirectory, { recursive: true, force: true }).catch(() => undefined);
  }
}

export async function runStoryGeneration(storyId: string, userId: string) {
  let temporaryDirectory: string | undefined;
  try {
    const story = await getStoryForUser(storyId, userId);
    if (!story) throw new Error("لا يمكن بدء التوليد لأن القصة غير موجودة أو لا تخص هذا المستخدم.");
    const outputMode = story.input.output?.trim() || "نص + صوت + فيديو";
    const wantsAudio = outputMode.includes("صوت") || outputMode.includes("فيديو");
    const wantsVisuals = outputMode.includes("فيديو");

    const durations = createSceneDurationPlan(story.totalDurationSeconds);
    temporaryDirectory = await mkdtemp(join(tmpdir(), `sard-${storyId.slice(0, 8)}-`));
    const workingDirectory = temporaryDirectory;

    let script = storedScriptForResume(story, durations);
    let scenes: StoryScene[];
    if (script) {
      scenes = story.scenes;
      await appendStoryLog(storyId, { level: "info", message: "استئناف القصة من السيناريو المحفوظ؛ لن يُعاد استدعاء Qwen للسيناريو." });
    } else {
      await logAndProgress(storyId, wantsVisuals ? 4 : wantsAudio ? 10 : 25, "استدعاء نموذج Qwen لإنشاء السيناريو العربي.");
      script = await generateScript(story.input, durations, async (message) => appendStoryLog(storyId, { level: "info", message }));
      scenes = script.scenes.map((scene) => ({ ...scene, imagePrompt: "", imageGenerationPrompt: "", videoPrompt: "" }));
      await saveGeneratedScript(storyId, { script: script.script, characters: script.characters, visualStyleGuide: script.visualStyleGuide, scenes });
    }

    if (!scenes.every((scene) => scene.narrationVocalized)) {
      await logAndProgress(storyId, wantsVisuals ? 12 : wantsAudio ? 25 : 70, "تشكيل النصوص العربية بدقة قبل إنشاء التعليق الصوتي.");
      const vocalizedNarrations = await vocalizeNarrations(scenes, async (message) => appendStoryLog(storyId, { level: "info", message }));
      await saveSceneNarrations(storyId, vocalizedNarrations);
      const narrationByScene = new Map(vocalizedNarrations.map((scene) => [scene.number, scene.narration]));
      scenes = scenes.map((scene) => ({ ...scene, narration: narrationByScene.get(scene.number)!, narrationVocalized: true }));
      script = { ...script, scenes: script.scenes.map((scene) => ({ ...scene, narration: narrationByScene.get(scene.number)! })) };
    }

    if (!wantsAudio && !wantsVisuals) {
      await completeStory(storyId, {});
      await appendStoryLog(storyId, { level: "info", message: "اكتمل إنشاء القصة النصية بنجاح وفق خيار نوع المخرجات (نص فقط)." });
      return;
    }

    const storyFolder = `/sard-ai/${storyId}`;
    if (!wantsVisuals) {
      const audioPaths = new Map<number, string>();
      const savedAudioCount = scenes.filter((scene) => scene.audioUrl && scene.audioDurationMatched).length;
      if (savedAudioCount) await appendStoryLog(storyId, { level: "info", message: `استئناف ${savedAudioCount} ملفاً صوتياً محفوظاً من ImageKit؛ ستُولّد الملفات الناقصة فقط.` });
      for (const pair of scenePairs(scenes)) {
        await logAndProgress(storyId, sceneProgress(30, 85, pair.at(-1)!.number, scenes.length), `توليد ورفع تعليقات المشاهد ${pair.map((scene) => scene.number).join(" و ")} بالتوازي.`);
        await Promise.all(pair.map(async (scene) => {
          if (scene.audioUrl && scene.audioDurationMatched) {
            const existingAudio = await requestBinary(scene.audioUrl, {}, `تنزيل صوت المشهد ${scene.number} من ImageKit`);
            const existingPath = join(workingDirectory, `scene-${scene.number}-voice.mp3`);
            await writeFile(existingPath, existingAudio.bytes);
            audioPaths.set(scene.number, existingPath);
            return;
          }
          const generated = join(workingDirectory, `scene-${scene.number}-voice.mp3`);
          const generatedSpeech = await generateSpeechForDuration(scene.narration, story.input.speakerGender, scene.durationSeconds, generated);
          if (generatedSpeech.narration !== scene.narration) await saveSceneNarration(storyId, scene.number, generatedSpeech.narration);
          const audioUrl = await uploadToImageKit(await readFile(generated), `scene-${scene.number}-voice.mp3`, `${storyFolder}/audio`, "audio/mpeg");
          await saveSceneAsset(storyId, scene.number, "audioUrl", audioUrl);
          audioPaths.set(scene.number, generated);
        }));
      }

      await logAndProgress(storyId, 92, "دمج التعليقات الصوتية في ملف صوتي موحد.");
      const combinedAudio = join(workingDirectory, "story-voice.mp3");
      const orderedAudioPaths = scenes.map((scene) => audioPaths.get(scene.number));
      if (orderedAudioPaths.some((path) => !path)) throw new Error("تعذر العثور على أحد ملفات الصوت لدمجها.");
      await concatenate(orderedAudioPaths as string[], combinedAudio, "audio", workingDirectory);
      const combinedAudioUrl = await uploadToImageKit(await readFile(combinedAudio), "story-voice.mp3", `${storyFolder}/final`, "audio/mpeg");

      await completeStory(storyId, { combinedAudioUrl });
      await appendStoryLog(storyId, { level: "info", message: "اكتمل إنشاء القصة والتعليق الصوتي الموحد بنجاح وفق خيار نوع المخرجات (نص + صوت)." });
      return;
    }

    const needsVisualPromptMigration = scenes.some((scene) => !scene.imageGenerationPrompt?.trim());
    let promptResult: GeneratedPrompts;
    if (!needsVisualPromptMigration && scenes.every((scene) => scene.imagePrompt.trim() && scene.imageGenerationPrompt?.trim() && scene.videoPrompt.trim())) {
      promptResult = validateGeneratedPrompts({ prompts: scenes.map(({ number, imagePrompt, imageGenerationPrompt, videoPrompt }) => ({ number, imagePrompt, imageGenerationPrompt, videoPrompt })) }, scenes.map((scene) => scene.number));
      await appendStoryLog(storyId, { level: "info", message: "استئناف القصة من مطالبات المشاهد المحفوظة؛ لن يُعاد استدعاء Qwen للمطالبات." });
    } else {
      if (needsVisualPromptMigration) {
        await appendStoryLog(storyId, { level: "info", message: "تحديث مطالبات الصور القديمة إلى مطالبات FLUX إنجليزية دقيقة قبل إعادة إنشاء الأصول المرئية." });
      }
      await logAndProgress(storyId, 16, "استدعاء نموذج Qwen لإنشاء مطالبات بصرية متسقة.");
      promptResult = await generateVisualPrompts(script, async (message) => appendStoryLog(storyId, { level: "info", message }));
      await saveScenePrompts(storyId, promptResult.prompts);
      const promptByScene = new Map(promptResult.prompts.map((prompt) => [prompt.number, prompt]));
      scenes = scenes.map((scene) => ({ ...scene, ...promptByScene.get(scene.number)! }));
    }

    const refreshLegacyVisualAssets = needsVisualPromptMigration && scenes.some((scene) => scene.imageUrl || scene.videoUrl);
    const imageUrls = new Map<number, string>(refreshLegacyVisualAssets ? [] : scenes.flatMap((scene) => scene.imageUrl ? [[scene.number, scene.imageUrl] as const] : []));
    const scenesNeedingImages = scenes.filter((scene) => refreshLegacyVisualAssets || !scene.imageUrl);
    if (refreshLegacyVisualAssets) {
      await appendStoryLog(storyId, { level: "info", message: "إعادة توليد الصور ومقاطع الفيديو المحفوظة لمرة واحدة لأنها أُنشئت قبل إضافة مطالبات FLUX الدقيقة." });
    } else if (imageUrls.size) {
      await appendStoryLog(storyId, { level: "info", message: `استئناف ${imageUrls.size} صورة محفوظة من ImageKit؛ ستُولّد الصور الناقصة فقط.` });
    }
    for (const pair of scenePairs(scenesNeedingImages)) {
      await logAndProgress(storyId, sceneProgress(22, 47, pair.at(-1)!.number, scenes.length), `توليد ورفع صور المشاهد ${pair.map((scene) => scene.number).join(" و ")} بالتوازي.`);
      await Promise.all(pair.map(async (scene) => {
        const prompt = promptResult.prompts[scene.number - 1].imageGenerationPrompt;
        const image = await generateImage(
          prompt,
          async (message) => appendStoryLog(storyId, { level: "info", message }),
          (scene.number - 1) % CONCURRENT_SCENE_GENERATIONS * 6_000,
        );
        const imageUrl = await uploadToImageKit(image.bytes, `scene-${scene.number}-image.${extensionFor(image.contentType, "png")}`, `${storyFolder}/images`, image.contentType);
        await saveSceneAsset(storyId, scene.number, "imageUrl", imageUrl);
        imageUrls.set(scene.number, imageUrl);
      }));
    }

    const audioPaths = new Map<number, string>();
    const savedAudioCount = scenes.filter((scene) => scene.audioUrl && scene.audioDurationMatched).length;
    if (savedAudioCount) await appendStoryLog(storyId, { level: "info", message: `استئناف ${savedAudioCount} ملفاً صوتياً محفوظاً من ImageKit؛ ستُولّد الملفات الناقصة فقط.` });
    for (const pair of scenePairs(scenes)) {
      await logAndProgress(storyId, sceneProgress(48, 67, pair.at(-1)!.number, scenes.length), `توليد ورفع تعليقات المشاهد ${pair.map((scene) => scene.number).join(" و ")} بالتوازي.`);
      await Promise.all(pair.map(async (scene) => {
        if (scene.audioUrl && scene.audioDurationMatched) {
          const existingAudio = await requestBinary(scene.audioUrl, {}, `تنزيل صوت المشهد ${scene.number} من ImageKit`);
          const existingPath = join(workingDirectory, `scene-${scene.number}-voice.mp3`);
          await writeFile(existingPath, existingAudio.bytes);
          audioPaths.set(scene.number, existingPath);
          return;
        }
        const generated = join(workingDirectory, `scene-${scene.number}-voice.mp3`);
        const generatedSpeech = await generateSpeechForDuration(scene.narration, story.input.speakerGender, scene.durationSeconds, generated);
        if (generatedSpeech.narration !== scene.narration) await saveSceneNarration(storyId, scene.number, generatedSpeech.narration);
        const audioUrl = await uploadToImageKit(await readFile(generated), `scene-${scene.number}-voice.mp3`, `${storyFolder}/audio`, "audio/mpeg");
        await saveSceneAsset(storyId, scene.number, "audioUrl", audioUrl);
        audioPaths.set(scene.number, generated);
      }));
    }

    const videoPaths = new Map<number, string>();
    const refreshLegacyVideoAssets = refreshLegacyVisualAssets || scenes.some((scene) => scene.videoUrl && scene.videoGenerator !== "openrouter-seedance-2.0");
    const savedVideoCount = refreshLegacyVideoAssets ? 0 : scenes.filter((scene) => scene.videoUrl).length;
    if (refreshLegacyVideoAssets) {
      await appendStoryLog(storyId, { level: "info", message: "إعادة توليد مقاطع الفيديو القديمة مرة واحدة عبر OpenRouter Seedance 2.0." });
    } else if (savedVideoCount) {
      await appendStoryLog(storyId, { level: "info", message: `استئناف ${savedVideoCount} فيديو محفوظاً من ImageKit؛ ستُولّد الفيديوهات الناقصة فقط.` });
    }
    for (const pair of scenePairs(scenes)) {
      await logAndProgress(storyId, sceneProgress(68, 91, pair.at(-1)!.number, scenes.length), `توليد ورفع فيديوهات المشاهد ${pair.map((scene) => scene.number).join(" و ")} بالتوازي.`);
      await Promise.all(pair.map(async (scene) => {
        if (scene.videoUrl && !refreshLegacyVideoAssets) {
          const existingVideo = await requestBinary(scene.videoUrl, {}, `تنزيل فيديو المشهد ${scene.number} من ImageKit`);
          const existingPath = join(workingDirectory, `scene-${scene.number}-video.mp4`);
          await writeFile(existingPath, existingVideo.bytes);
          videoPaths.set(scene.number, existingPath);
          return;
        }
        const imageUrl = imageUrls.get(scene.number);
        if (!imageUrl) throw new Error(`صورة المشهد ${scene.number} غير متاحة لتوليد الفيديو.`);
        const video = await generateVideo(imageUrl, promptResult.prompts[scene.number - 1].videoPrompt, scene.durationSeconds);
        const source = join(workingDirectory, `scene-${scene.number}-video-source.${extensionFor(video.contentType, "mp4")}`);
        const trimmed = join(workingDirectory, `scene-${scene.number}-video.mp4`);
        await writeFile(source, video.bytes);
        await trimVideo(source, trimmed, scene.durationSeconds);
        const trimmedBytes = await readFile(trimmed);
        const videoUrl = await uploadToImageKit(trimmedBytes, `scene-${scene.number}-video.mp4`, `${storyFolder}/videos`, "video/mp4");
        await saveSceneVideoAsset(storyId, scene.number, videoUrl);
        videoPaths.set(scene.number, trimmed);
      }));
    }

    await logAndProgress(storyId, 92, "دمج المقاطع المرئية من دون صوت.");
    const combinedVideo = join(workingDirectory, "story-video.mp4");
    const orderedVideoPaths = scenes.map((scene) => videoPaths.get(scene.number));
    if (orderedVideoPaths.some((path) => !path)) throw new Error("تعذر العثور على أحد مقاطع الفيديو لدمجها.");
    await concatenate(orderedVideoPaths as string[], combinedVideo, "video", workingDirectory, story.totalDurationSeconds);
    const combinedVideoUrl = await uploadToImageKit(await readFile(combinedVideo), "story-video.mp4", `${storyFolder}/final`, "video/mp4");

    await logAndProgress(storyId, 96, "دمج التعليقات الصوتية في ملف صوتي منفصل.");
    const combinedAudio = join(workingDirectory, "story-voice.mp3");
    const orderedAudioPaths = scenes.map((scene) => audioPaths.get(scene.number));
    if (orderedAudioPaths.some((path) => !path)) throw new Error("تعذر العثور على أحد ملفات الصوت لدمجها.");
    await concatenate(orderedAudioPaths as string[], combinedAudio, "audio", workingDirectory);
    const combinedAudioUrl = await uploadToImageKit(await readFile(combinedAudio), "story-voice.mp3", `${storyFolder}/final`, "audio/mpeg");

    await logAndProgress(storyId, 98, "دمج الفيديو الموحد مع التعليق الصوتي في ملف نهائي.");
    const combinedNarratedVideo = join(workingDirectory, "story-narrated-video.mp4");
    await mergeVideoWithAudio(combinedVideo, combinedAudio, combinedNarratedVideo);
    const combinedNarratedVideoUrl = await uploadToImageKit(await readFile(combinedNarratedVideo), "story-narrated-video.mp4", `${storyFolder}/final`, "video/mp4");

    await completeStory(storyId, { combinedAudioUrl, combinedVideoUrl, combinedNarratedVideoUrl });
    await appendStoryLog(storyId, { level: "info", message: "اكتمل التوليد ورفع جميع الأصول إلى ImageKit." });
  } catch (error) {
    const message = error instanceof Error ? safeProviderText(error.message) : "حدث خطأ غير معروف أثناء توليد القصة.";
    await failStory(storyId, message).catch((persistError) => console.error("[Sard] تعذر حفظ خطأ التوليد:", persistError));
    await appendStoryLog(storyId, { level: "error", message }).catch((persistError) => console.error("[Sard] تعذر حفظ سجل الخطأ:", persistError));
    console.error(`[Sard][${storyId}] فشل التوليد:`, message);
  } finally {
    if (temporaryDirectory) await rm(temporaryDirectory, { recursive: true, force: true }).catch(() => undefined);
  }
}

export function newStoryId() {
  return randomUUID();
}
