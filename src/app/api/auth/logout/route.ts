import { clearSession } from "@/server/auth/session";
import { handleApiError } from "@/server/errors/error-handler";
import { apiSuccess } from "@/server/responses/api-response";
import { assertSameOrigin } from "@/server/security/request-origin";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    assertSameOrigin(request);
    await clearSession();
    return apiSuccess(null, "تم تسجيل الخروج بنجاح.");
  } catch (error) {
    return handleApiError(error, { route: "POST /api/auth/logout" });
  }
}
