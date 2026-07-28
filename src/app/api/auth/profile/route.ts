import { updateProfileRequestSchema } from "@/server/auth/auth.schemas";
import { updateUserProfile } from "@/server/auth/auth.service";
import { requireUser } from "@/server/auth/session";
import { handleApiError } from "@/server/errors/error-handler";
import { apiSuccess } from "@/server/responses/api-response";
import { parseJsonBody } from "@/server/validation/common.schemas";
import { assertSameOrigin } from "@/server/security/request-origin";

export const runtime = "nodejs";

export async function PATCH(request: Request) {
  try {
    assertSameOrigin(request);
    const user = await requireUser();
    const input = await parseJsonBody(request, updateProfileRequestSchema, 20_000);
    const updatedUser = await updateUserProfile(user.id, input);
    return apiSuccess(updatedUser, "تم تحديث الملف الشخصي بنجاح.");
  } catch (error) {
    return handleApiError(error, { route: "PATCH /api/auth/profile" });
  }
}
