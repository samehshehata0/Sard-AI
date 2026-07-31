import { getDatabaseStatus } from "@/server/database/connection";
import { handleApiError } from "@/server/errors/error-handler";
import { apiSuccess } from "@/server/responses/api-response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const database = await getDatabaseStatus();
    return apiSuccess(
      {
        api: "ok",
        database,
        timestamp: new Date().toISOString(),
      },
      database === "connected" ? "الخدمة تعمل بصورة طبيعية." : "الخدمة تعمل، لكن قاعدة البيانات غير متاحة.",
      { status: database === "connected" ? 200 : 503 },
    );
  } catch (error) {
    return handleApiError(error, { route: "GET /api/health" });
  }
}
