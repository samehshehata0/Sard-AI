import { after } from "next/server";
import { getStoryForUser, resetStoryForRetry } from "@/lib/story-repository";
import { runStoryGeneration } from "@/lib/services/story-generation";

export const runtime = "nodejs";
export const maxDuration = 900;
export const dynamic = "force-dynamic";

const USER_COOKIE = "sard_user_id";

function getUserId(request: Request) {
  const cookieHeader = request.headers.get("cookie") || "";
  return cookieHeader.match(new RegExp(`(?:^|;\\s*)${USER_COOKIE}=([^;]+)`))?.[1];
}

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const userId = getUserId(request);
  if (!userId) return Response.json({ error: "تعذر تحديد مستخدم القصة." }, { status: 401 });
  const { id } = await context.params;
  try {
    const story = await getStoryForUser(id, userId);
    if (!story) return Response.json({ error: "القصة غير موجودة أو لا تملك صلاحية الوصول إليها." }, { status: 404 });
    if (story.status !== "failed") return Response.json({ error: "لا يمكن إعادة المحاولة إلا لقصة توقفت بسبب خطأ." }, { status: 409 });
    if (!await resetStoryForRetry(id, userId)) return Response.json({ error: "تعذر تجهيز القصة لإعادة المحاولة." }, { status: 409 });
    after(async () => { await runStoryGeneration(id, userId); });
    return Response.json({ status: "queued" }, { status: 202 });
  } catch (error) {
    console.error(`[Sard][${id}] تعذرت إعادة محاولة التوليد:`, error);
    return Response.json({ error: "تعذرت إعادة محاولة التوليد. راجع طرفية الخادم للتفاصيل." }, { status: 500 });
  }
}
