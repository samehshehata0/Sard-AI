import { failStory, getStoryForUser } from "@/lib/story-repository";
import { requireStoryUserId } from "@/lib/story-auth";
import { cancelStoryJob } from "@/lib/services/job-queue";
import { assertSameOrigin } from "@/server/security/request-origin";
import { apiSuccess } from "@/server/responses/api-response";
import { handleApiError } from "@/server/errors/error-handler";
import { AppError } from "@/server/errors/app-error";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CANCELLED_MESSAGE = "أُلغي طلب التوليد.";

/** Cancel a story that is still waiting in the queue. One that is already being generated cannot be cancelled. */
export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  try {
    assertSameOrigin(request);
    const userId = await requireStoryUserId();

    const story = await getStoryForUser(id, userId);
    if (!story) throw AppError.notFound("القصة غير موجودة أو لا تملك صلاحية الوصول إليها.");
    if (!story.jobId || (story.status !== "queued" && story.status !== "generating")) {
      throw AppError.conflict("لا يمكن إلغاء طلب انتهت معالجته.");
    }

    // The queue has the final say: it refuses a Job that a worker has already started.
    await cancelStoryJob(story.jobId, userId);
    await failStory(id, CANCELLED_MESSAGE);

    return apiSuccess({ status: "cancelled" }, "تم إلغاء طلب التوليد.");
  } catch (error) {
    return handleApiError(error, { route: "POST /api/stories/[id]/cancel", storyId: id });
  }
}
