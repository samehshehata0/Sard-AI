import { ZodError } from "zod";
import { AppError } from "@/server/errors/app-error";
import { logger } from "@/server/logging/logger";
import { apiFailure } from "@/server/responses/api-response";

function zodDetails(error: ZodError) {
  return error.issues.map((issue) => ({ field: issue.path.join("."), message: issue.message }));
}

export function handleApiError(error: unknown, context?: Record<string, unknown>): Response {
  if (error instanceof ZodError) {
    return apiFailure("VALIDATION_ERROR", "البيانات المرسلة غير صالحة.", zodDetails(error), 400);
  }
  if (error instanceof AppError) {
    if (error.statusCode >= 500) logger.error(error.message, { ...context, code: error.code });
    return apiFailure(error.code, error.message, error.details, error.statusCode);
  }
  logger.error("Unhandled API error", {
    ...context,
    errorName: error instanceof Error ? error.name : "UnknownError",
    errorMessage: error instanceof Error ? error.message : String(error),
  });
  return apiFailure("INTERNAL_SERVER_ERROR", "حدث خطأ داخلي. يرجى المحاولة لاحقًا.", undefined, 500);
}
