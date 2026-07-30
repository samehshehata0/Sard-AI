import { getStoryForUser } from "@/lib/story-repository";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const USER_COOKIE = "sard_user_id";

function getUserId(request: Request) {
  const cookieHeader = request.headers.get("cookie") || "";
  return cookieHeader.match(new RegExp(`(?:^|;\\s*)${USER_COOKIE}=([^;]+)`))?.[1];
}

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const userId = getUserId(request);
  if (!userId) return Response.json({ error: "تعذر تحديد مستخدم القصة. أنشئ القصة من هذا المتصفح أولاً." }, { status: 401 });

  const { id } = await context.params;
  try {
    const story = await getStoryForUser(id, userId);
    if (!story) return Response.json({ error: "القصة غير موجودة أو لا تملك صلاحية الوصول إليها." }, { status: 404 });
    return Response.json({ story });
  } catch (error) {
    console.error(`[Sard][${id}] تعذر قراءة القصة من MongoDB:`, error);
    return Response.json({ error: "تعذر قراءة القصة من MongoDB. راجع طرفية الخادم للتفاصيل." }, { status: 500 });
  }
}
