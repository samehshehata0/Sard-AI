import { requireStoryUserId } from "@/lib/story-auth";
import { assertSameOrigin } from "@/server/security/request-origin";
import { apiSuccess } from "@/server/responses/api-response";
import { handleApiError } from "@/server/errors/error-handler";

export const runtime = "nodejs";
export const maxDuration = 900;
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    assertSameOrigin(request);
    await requireStoryUserId();

    return apiSuccess({ status: "completed" }, "توليد الفيديوهات يدار عبر Google NotebookLM تلقائياً.");
  } catch (error) {
    return handleApiError(error, { route: "POST /api/stories/[id]/video/rebuild" });
  }
}
