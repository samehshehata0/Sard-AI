import { rebuildStoryVideoToRequestedDuration } from "@/lib/services/story-generation";

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
    await rebuildStoryVideoToRequestedDuration(id, userId);
    return Response.json({ status: "completed" });
  } catch (error) {
    console.error(`[Sard][${id}] تعذر إصلاح مدة الفيديو:`, error);
    return Response.json(
      { error: error instanceof Error ? error.message : "تعذر إصلاح مدة الفيديو." },
      { status: 500 },
    );
  }
}
