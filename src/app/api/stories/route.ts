import { randomUUID } from "node:crypto";
import { after } from "next/server";
import { createQueuedStory, createStory, ensureUser, listStoriesForUser } from "@/lib/story-repository";
import { createSceneDurationPlan, newStoryId, parseArabicDurationToSeconds, runStoryGeneration } from "@/lib/services/story-generation";
import { storyGenerationSchema } from "@/lib/story-request-schema";

export const runtime = "nodejs";
export const maxDuration = 900;
export const dynamic = "force-dynamic";

const USER_COOKIE = "sard_user_id";

function getOrCreateUserId(request: Request) {
  const cookieHeader = request.headers.get("cookie") || "";
  const existing = cookieHeader.match(new RegExp(`(?:^|;\\s*)${USER_COOKIE}=([^;]+)`))?.[1];
  return { userId: existing || `anonymous-${randomUUID()}`, isNew: !existing };
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "بيانات الطلب ليست JSON صالحاً." }, { status: 400 });
  }

  const parsed = storyGenerationSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: "تحقق من الحقول المطلوبة باللغة العربية قبل بدء التوليد." }, { status: 400 });
  }

  let totalDurationSeconds: number;
  try {
    totalDurationSeconds = parseArabicDurationToSeconds(parsed.data.duration);
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "مدة القصة غير صالحة." }, { status: 400 });
  }

  const { userId, isNew } = getOrCreateUserId(request);
  const storyId = newStoryId();
  let sceneCount: number;
  try {
    sceneCount = createSceneDurationPlan(totalDurationSeconds).length;
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "تعذر حساب عدد المشاهد." }, { status: 400 });
  }

  try {
    await ensureUser(userId);
    await createStory(createQueuedStory(storyId, userId, parsed.data, totalDurationSeconds, sceneCount));
  } catch (error) {
    console.error("[Sard] تعذر إنشاء مستند القصة في MongoDB:", error);
    return Response.json({ error: "تعذر إنشاء مستند القصة في MongoDB. راجع طرفية الخادم للتفاصيل." }, { status: 500 });
  }

  after(async () => {
    await runStoryGeneration(storyId, userId);
  });

  const response = Response.json({ storyId, status: "queued", sceneCount }, { status: 202 });
  if (isNew) {
    response.headers.append("Set-Cookie", `${USER_COOKIE}=${encodeURIComponent(userId)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000${process.env.NODE_ENV === "production" ? "; Secure" : ""}`);
  }
  return response;
}

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") || "";
  const userId = cookieHeader.match(new RegExp(`(?:^|;\\s*)${USER_COOKIE}=([^;]+)`))?.[1];
  if (!userId) return Response.json({ stories: [] });
  try {
    return Response.json({ stories: await listStoriesForUser(userId) });
  } catch (error) {
    console.error("[Sard] تعذر تحميل سجل القصص من MongoDB:", error);
    return Response.json({ error: "تعذر تحميل سجل القصص من MongoDB." }, { status: 500 });
  }
}
