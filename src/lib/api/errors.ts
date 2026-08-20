import type { ApiErrorBody, ApiFieldErrors } from "@/types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly details: ApiFieldErrors = {},
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
    normalizeFieldErrors(error?.details),
    error?.requestId,
  );
}

function normalizeFieldErrors(details: unknown): ApiFieldErrors {
  if (Array.isArray(details)) {
    return Object.fromEntries(
      details.flatMap((item) =>
        item && typeof item === "object" && "field" in item && "message" in item &&
        typeof item.field === "string" && typeof item.message === "string"
          ? [[item.field, item.message]]
          : [],
      ),
    );
  }
  if (!details || typeof details !== "object") return {};
  return Object.fromEntries(Object.entries(details).filter((entry): entry is [string, string] => typeof entry[1] === "string"));
}
