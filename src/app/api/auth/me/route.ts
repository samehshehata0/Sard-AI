import { requireUser } from "@/server/auth/session";
import { handleApiError } from "@/server/errors/error-handler";
import { apiSuccess } from "@/server/responses/api-response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const user = await requireUser();
    return apiSuccess(user, "تم جلب بيانات المستخدم.");
  } catch (error) {
    return handleApiError(error, { route: "GET /api/auth/me" });
  }
}
