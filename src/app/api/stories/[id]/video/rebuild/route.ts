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
  return Response.json({ status: "completed", message: "توليد الفيديوهات يدار عبر Google NotebookLM تلقائياً." });
}
