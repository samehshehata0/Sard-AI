import { randomUUID } from "node:crypto";
import { failStory, getStoryForUser, resetStoryForRetry } from "@/lib/story-repository";
import { requireStoryUserId } from "@/lib/story-auth";
import { enqueueStoryJob } from "@/lib/services/job-queue";
import { assertSameOrigin } from "@/server/security/request-origin";
import { apiSuccess } from "@/server/responses/api-response";
import { handleApiError } from "@/server/errors/error-handler";
import { AppError } from "@/server/errors/app-error";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  try {
    assertSameOrigin(request);
    const userId = await requireStoryUserId();

    const story = await getStoryForUser(id, userId);
    if (!story) throw AppError.notFound("القصة غير موجودة أو لا تملك صلاحية الوصول إليها.");
    if (story.status !== "failed") throw AppError.conflict("لا يمكن إعادة المحاولة إلا لقصة توقفت بسبب خطأ.");

    const jobId = randomUUID();
    if (!(await resetStoryForRetry(id, userId, jobId))) throw AppError.conflict("تعذر تجهيز القصة لإعادة المحاولة.");

    try {
      const outcome = await enqueueStoryJob(id, jobId, userId, story.input);
      if (outcome.duplicate) {
        throw AppError.conflict("يوجد طلب مطابق قيد المعالجة بالفعل.");
      }
    } catch (err) {
      const message = err instanceof AppError ? err.message : "تعذر إضافة طلب التوليد إلى قائمة الانتظار.";
      await failStory(id, message).catch(() => {});
      throw err;
    }

    return apiSuccess({ status: "queued" }, "أعيدت محاولة التوليد بنجاح.", { status: 202 });
  } catch (error) {
    return handleApiError(error, { route: "POST /api/stories/[id]/retry", storyId: id });
  }
}
