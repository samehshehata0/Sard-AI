import { loginRequestSchema } from "@/server/auth/auth.schemas";
import { loginUser } from "@/server/auth/auth.service";
import { enforceLoginRateLimit, resetLoginRateLimit } from "@/server/auth/rate-limit";
import { handleApiError } from "@/server/errors/error-handler";
import { apiSuccess } from "@/server/responses/api-response";
import { parseJsonBody } from "@/server/validation/common.schemas";
import { assertSameOrigin } from "@/server/security/request-origin";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    assertSameOrigin(request);
    const input = await parseJsonBody(request, loginRequestSchema, 10_000);
    enforceLoginRateLimit(request, input.email);
    const user = await loginUser(input);
    resetLoginRateLimit(request, input.email);
    return apiSuccess({ user }, "تم تسجيل الدخول بنجاح.");
  } catch (error) {
    return handleApiError(error, { route: "POST /api/auth/login" });
  }
}
