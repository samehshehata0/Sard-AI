import { registerRequestSchema } from "@/server/auth/auth.schemas";
import { registerUser } from "@/server/auth/auth.service";
import { handleApiError } from "@/server/errors/error-handler";
import { apiSuccess } from "@/server/responses/api-response";
import { parseJsonBody } from "@/server/validation/common.schemas";
import { assertSameOrigin } from "@/server/security/request-origin";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    assertSameOrigin(request);
    const input = await parseJsonBody(request, registerRequestSchema, 20_000);
    const user = await registerUser(input);
    return apiSuccess({ user }, "تم إنشاء الحساب بنجاح.", { status: 201 });
  } catch (error) {
    return handleApiError(error, { route: "POST /api/auth/register" });
  }
}
