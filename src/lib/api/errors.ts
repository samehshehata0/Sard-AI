import type { ApiErrorBody, ApiFieldError } from "@/types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly details: ApiFieldError[] = [],
    public readonly requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function normalizeApiError(status: number, payload: unknown): ApiError {
  const body = payload as Partial<ApiErrorBody> | null;
  const error = body?.error;
  return new ApiError(
    error?.message ?? "تعذر إكمال الطلب. حاول مرة أخرى.",
    status,
    error?.code ?? (status === 0 ? "NETWORK_ERROR" : "UNKNOWN_ERROR"),
    error?.details ?? [],
    error?.requestId,
  );
}
