import type { AppErrorCode } from "@/server/errors/app-error";

export interface SuccessPayload<T> {
  success: true;
  data: T;
  message: string;
}

export interface FailurePayload {
  success: false;
  error: {
    code: AppErrorCode;
    message: string;
    details?: unknown;
  };
}

export function successPayload<T>(data: T, message = "تم تنفيذ الطلب بنجاح."): SuccessPayload<T> {
  return { success: true, data, message };
}

export function failurePayload(code: AppErrorCode, message: string, details?: unknown): FailurePayload {
  return { success: false, error: { code, message, ...(details === undefined ? {} : { details }) } };
}

export function apiSuccess<T>(data: T, message?: string, init?: ResponseInit) {
  return Response.json(successPayload(data, message), init);
}

export function apiFailure(code: AppErrorCode, message: string, details: unknown, status: number) {
  return Response.json(failurePayload(code, message, details), { status });
}
