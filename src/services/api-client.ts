import { normalizeApiError } from "@/lib/api/errors";
import type { ApiSuccess } from "@/types/api";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export const isApiConfigured = API_URL.length > 0;

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  token?: string;
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { body, headers, token, ...requestOptions } = options;
  let response: Response;

  try {
    response = await fetch(`${API_URL}${path}`, {
      ...requestOptions,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: requestOptions.credentials ?? "include",
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
    });
  } catch {
    throw normalizeApiError(0, null);
  }

  const payload = response.status === 204 ? undefined : await response.json().catch(() => undefined);
  if (!response.ok) throw normalizeApiError(response.status, payload);

  const envelope = payload as ApiSuccess<T> | T;
  return envelope && typeof envelope === "object" && "data" in envelope ? envelope.data : (envelope as T);
}

export async function apiRequestEnvelope<T>(path: string, options: ApiRequestOptions = {}): Promise<ApiSuccess<T>> {
  const { body, headers, token, ...requestOptions } = options;
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...requestOptions,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: requestOptions.credentials ?? "include",
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
    });
  } catch {
    throw normalizeApiError(0, null);
  }
  const payload = await response.json().catch(() => undefined);
  if (!response.ok) throw normalizeApiError(response.status, payload);
  return payload as ApiSuccess<T>;
}
