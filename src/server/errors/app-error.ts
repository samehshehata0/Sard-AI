export type AppErrorCode =
  | "VALIDATION_ERROR"
  | "AUTHENTICATION_ERROR"
  | "AUTHORIZATION_ERROR"
  | "NOT_FOUND"
  | "CONFLICT"
  | "PROVIDER_FAILURE"
  | "RATE_LIMITED"
  | "PAYLOAD_TOO_LARGE"
  | "DATABASE_UNAVAILABLE"
  | "INTERNAL_SERVER_ERROR";

export class AppError extends Error {
  constructor(
    public readonly code: AppErrorCode,
    public readonly statusCode: number,
    message: string,
    public readonly details?: unknown,
    public readonly isOperational = true,
  ) {
    super(message);
    this.name = "AppError";
  }

  static validation(details?: unknown, message = "البيانات المرسلة غير صالحة.") {
    return new AppError("VALIDATION_ERROR", 400, message, details);
  }
  static authentication(message = "يرجى تسجيل الدخول للمتابعة.") {
    return new AppError("AUTHENTICATION_ERROR", 401, message);
  }
  static authorization(message = "ليس لديك صلاحية لتنفيذ هذا الإجراء.") {
    return new AppError("AUTHORIZATION_ERROR", 403, message);
  }
  static notFound(message = "المورد المطلوب غير موجود.") {
    return new AppError("NOT_FOUND", 404, message);
  }
  static conflict(message = "يتعارض الطلب مع الحالة الحالية للمورد.") {
    return new AppError("CONFLICT", 409, message);
  }
  static providerFailure(message = "تعذر إكمال الطلب لدى مزود الخدمة.") {
    return new AppError("PROVIDER_FAILURE", 502, message);
  }
  static rateLimited(message = "تم تجاوز عدد الطلبات المسموح. حاول لاحقًا.") {
    return new AppError("RATE_LIMITED", 429, message);
  }
  static payloadTooLarge(message = "حجم الطلب أكبر من الحد المسموح.") {
    return new AppError("PAYLOAD_TOO_LARGE", 413, message);
  }
  static databaseUnavailable(message = "قاعدة البيانات غير متاحة مؤقتًا.") {
    return new AppError("DATABASE_UNAVAILABLE", 503, message);
  }
  static internal(message = "حدث خطأ داخلي. يرجى المحاولة لاحقًا.") {
    return new AppError("INTERNAL_SERVER_ERROR", 500, message, undefined, false);
  }
}
